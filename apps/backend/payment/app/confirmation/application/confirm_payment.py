from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from app.confirmation.application import confirmation_event_names as names
from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.confirmation.domain.exceptions.intent_not_confirmable_error import (
    IntentNotConfirmableError,
)
from app.confirmation.domain.interfaces.confirmation_unit_of_work import ConfirmationUnitOfWork
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.confirmation.domain.value_objects.confirmation_fingerprint import ConfirmationFingerprint
from app.core.events.business_event import BusinessEvent, Scalar
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction


class ConfirmPaymentUseCase:
    """Confirme une intention : une seule fois, de façon idempotente, état et grand livre ensemble.

    Le montant vient toujours de l'intention stockée, jamais de la demande. L'intention est
    verrouillée (ligne) pendant tout le traitement : deux confirmations concurrentes se suivent.
    Les événements de résultat ne sont journalisés qu'après la validation de la transaction.
    """

    def __init__(
        self,
        unit_of_work: ConfirmationUnitOfWork,
        provider: PaymentProvider,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._provider = provider
        self._clock = clock
        self._events = events

    def execute(self, command: ConfirmPaymentCommand) -> PaymentIntentView:
        intent_id = self._parse(command)
        method = PaymentMethod(command.payment_method)
        fingerprint = ConfirmationFingerprint.of(intent_id, method)
        with self._unit_of_work.begin() as session:
            intent = session.lock_intent(intent_id)
            if intent is None:
                self._reject(command, "intent_not_found", str(intent_id))
                raise PaymentIntentNotFoundError
            existing = session.find_record(command.caller, command.idempotency_key)
            if existing:
                return self._replay(existing, intent, fingerprint, command)
            now = self._clock()
            if not intent.can_be_confirmed(now):
                self._reject(command, self._refusal_reason(intent, now), str(intent.id), intent)
                raise IntentNotConfirmableError
            outcome = self._provider.authorize(method, intent.amount)
            settled, ledger = self._settle(intent, outcome, now)
            record = ConfirmationRecord(
                command.caller, command.idempotency_key, fingerprint, intent.id
            )
            session.save(settled, record, ledger)
        self._log_settlement(command, settled, outcome, ledger)
        return PaymentIntentView.from_entity(settled)

    def _parse(self, command: ConfirmPaymentCommand) -> UUID:
        try:
            return UUID(command.intent_id)
        except ValueError:
            self._reject(command, "intent_not_found", None)
            raise PaymentIntentNotFoundError from None

    @staticmethod
    def _settle(
        intent: PaymentIntent, outcome: ProviderOutcome, now: datetime
    ) -> tuple[PaymentIntent, LedgerTransaction | None]:
        if outcome is ProviderOutcome.APPROVED:
            return intent.succeed(), LedgerTransaction.payment_received(
                intent.id, intent.amount, now
            )
        return intent.fail(), None

    def _replay(
        self,
        record: ConfirmationRecord,
        intent: PaymentIntent,
        fingerprint: str,
        command: ConfirmPaymentCommand,
    ) -> PaymentIntentView:
        if record.request_hash != fingerprint:
            self._reject(command, "idempotency_key_reused", str(intent.id), intent)
            raise ConfirmationKeyReusedError
        return PaymentIntentView.from_entity(intent)

    def _log_settlement(
        self,
        command: ConfirmPaymentCommand,
        settled: PaymentIntent,
        outcome: ProviderOutcome,
        ledger: LedgerTransaction | None,
    ) -> None:
        fields = self._fields(command, str(settled.id), self._attributes(settled))
        if outcome is ProviderOutcome.APPROVED:
            self._events.log(BusinessEvent.success(names.PAYMENT_CONFIRMED, **fields))
        elif outcome is ProviderOutcome.DECLINED:
            self._events.log(
                BusinessEvent.denied(names.PAYMENT_DECLINED, "provider_declined", **fields)
            )
        else:
            self._events.log(
                BusinessEvent.error(names.PAYMENT_TIMEOUT, "provider_timeout", **fields)
            )
        if ledger:
            written: dict[str, Scalar] = {
                "transaction_id": str(ledger.id),
                "entry_count": len(ledger.entries),
                "amount_cents": settled.amount.cents,
            }
            self._events.log(
                BusinessEvent.success(
                    names.LEDGER_ENTRIES_WRITTEN,
                    **self._fields(command, str(settled.id), written),
                )
            )

    def _reject(
        self,
        command: ConfirmPaymentCommand,
        reason: str,
        intent_id: str | None,
        intent: PaymentIntent | None = None,
    ) -> None:
        attributes = self._attributes(intent) if intent else {}
        self._events.log(
            BusinessEvent.denied(
                names.PAYMENT_CONFIRMATION_REJECTED,
                reason,
                **self._fields(command, intent_id, attributes),
            )
        )

    @staticmethod
    def _fields(
        command: ConfirmPaymentCommand, intent_id: str | None, attributes: Mapping[str, Scalar]
    ) -> dict[str, object]:
        """Ressource et acteur de l'événement : jamais la clé d'idempotence ni la valeur reçue."""
        return {
            "resource_type": "payment_intent",
            "resource_id": intent_id,
            "actor_type": "service",
            "actor_id": command.caller,
            "attributes": attributes,
        }

    @staticmethod
    def _attributes(intent: PaymentIntent) -> dict[str, Scalar]:
        return {
            "order_reference": intent.order_reference,
            "amount_cents": intent.amount.cents,
            "currency": intent.currency.value,
        }

    @staticmethod
    def _refusal_reason(intent: PaymentIntent, now: datetime) -> str:
        if intent.status is IntentStatus.REQUIRES_CONFIRMATION and now >= intent.expires_at:
            return "expired"
        return f"status_{intent.status.value}"
