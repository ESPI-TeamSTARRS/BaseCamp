from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.cancellation.application import cancellation_event_names as names
from app.cancellation.application.commands.cancel_payment_command import CancelPaymentCommand
from app.cancellation.domain.exceptions.intent_not_cancelable_error import (
    IntentNotCancelableError,
)
from app.cancellation.domain.interfaces.cancellation_unit_of_work import CancellationUnitOfWork
from app.core.events.business_event import BusinessEvent, Scalar
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError


class CancelPaymentIntentUseCase:
    """Annule une intention non confirmée, de façon idempotente et sans état en mémoire.

    L'intention est verrouillée (ligne) pendant tout le traitement : une confirmation concurrente
    attend puis constate l'annulation (409), et une intention déjà confirmée ne s'annule plus.
    Annuler deux fois la même intention rend le même résultat sans nouvel événement.
    """

    def __init__(
        self,
        unit_of_work: CancellationUnitOfWork,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._events = events

    def execute(self, command: CancelPaymentCommand) -> PaymentIntentView:
        intent_id = self._parse(command)
        with self._unit_of_work.begin() as session:
            intent = session.lock_intent(intent_id)
            if intent is None:
                self._reject(command, "intent_not_found", str(intent_id))
                raise PaymentIntentNotFoundError
            if intent.status is IntentStatus.CANCELED:
                return PaymentIntentView.from_entity(intent)
            now = self._clock()
            if not intent.can_be_canceled(now):
                self._reject(command, self._refusal_reason(intent, now), str(intent.id), intent)
                raise IntentNotCancelableError
            canceled = intent.cancel()
            session.save(canceled)
        self._events.log(
            BusinessEvent.success(
                names.PAYMENT_CANCELED, **self._fields(command, str(canceled.id), canceled)
            )
        )
        return PaymentIntentView.from_entity(canceled)

    def _parse(self, command: CancelPaymentCommand) -> UUID:
        try:
            return UUID(command.intent_id)
        except ValueError:
            self._reject(command, "intent_not_found", None)
            raise PaymentIntentNotFoundError from None

    def _reject(
        self,
        command: CancelPaymentCommand,
        reason: str,
        intent_id: str | None,
        intent: PaymentIntent | None = None,
    ) -> None:
        self._events.log(
            BusinessEvent.denied(
                names.PAYMENT_CANCELLATION_REJECTED,
                reason,
                **self._fields(command, intent_id, intent),
            )
        )

    @staticmethod
    def _fields(
        command: CancelPaymentCommand, intent_id: str | None, intent: PaymentIntent | None
    ) -> dict[str, object]:
        """Ressource et acteur de l'événement : jamais la valeur reçue."""
        attributes: dict[str, Scalar] = (
            {
                "order_reference": intent.order_reference,
                "amount_cents": intent.amount.cents,
                "currency": intent.currency.value,
            }
            if intent
            else {}
        )
        return {
            "resource_type": "payment_intent",
            "resource_id": intent_id,
            "actor_type": "service",
            "actor_id": command.caller,
            "attributes": attributes,
        }

    @staticmethod
    def _refusal_reason(intent: PaymentIntent, now: datetime) -> str:
        if intent.status is IntentStatus.REQUIRES_CONFIRMATION and intent.is_overdue(now):
            return "expired"
        return f"status_{intent.status.value}"
