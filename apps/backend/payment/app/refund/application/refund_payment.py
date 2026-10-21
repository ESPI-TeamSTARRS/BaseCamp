from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from app.core.events.business_event import BusinessEvent, Scalar
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.refund.application import refund_event_names as names
from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.application.dtos.refund_view import RefundView
from app.refund.domain.entities.refund import Refund
from app.refund.domain.exceptions.intent_not_refundable_error import IntentNotRefundableError
from app.refund.domain.exceptions.refund_exceeds_captured_error import RefundExceedsCapturedError
from app.refund.domain.exceptions.refund_key_reused_error import RefundKeyReusedError
from app.refund.domain.interfaces.refund_unit_of_work import RefundUnitOfWork
from app.refund.domain.value_objects.refund_fingerprint import RefundFingerprint
from app.webhook.application import webhook_event_names as webhook_names
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.services.refund_event_factory import RefundEventFactory


class RefundPaymentUseCase:
    """Rembourse tout ou partie d'un paiement : idempotent, sans jamais rendre plus que le capturé.

    L'intention est verrouillée (ligne) pendant tout le traitement : deux remboursements
    concurrents se suivent, le second voit le cumul validé du premier. L'état, le grand livre,
    le remboursement et l'événement du webhook sont écrits dans la même transaction. Les
    événements de résultat ne sont journalisés qu'après sa validation.
    """

    def __init__(
        self,
        unit_of_work: RefundUnitOfWork,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
        event_factory: RefundEventFactory | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._events = events
        self._event_factory = event_factory or RefundEventFactory()

    def execute(self, command: RefundPaymentCommand) -> RefundView:
        intent_id = self._parse(command)
        amount = Amount(command.amount)
        fingerprint = RefundFingerprint.of(intent_id, amount)
        with self._unit_of_work.begin() as session:
            intent = session.lock_intent(intent_id)
            if intent is None:
                self._reject(command, "intent_not_found", str(intent_id))
                raise PaymentIntentNotFoundError
            existing = session.find_refund(command.caller, command.idempotency_key)
            if existing:
                return self._replay(existing, intent, fingerprint, command)
            self._ensure_refundable(intent, amount, command)
            now = self._clock()
            refunded = intent.refund(amount)
            refund = Refund.issue(
                intent.id,
                amount,
                refunded.refunded_amount,
                command.caller,
                command.idempotency_key,
                fingerprint,
                now,
            )
            ledger = LedgerTransaction.refund_issued(intent.id, amount, now)
            outbox_event = self._event_factory.build(refunded, refund.id, amount, now)
            session.save(refunded, refund, ledger, outbox_event)
        self._log_refund(command, refund, refunded, ledger)
        self._log_queued(outbox_event)
        return RefundView.from_entities(refund, refunded)

    def _parse(self, command: RefundPaymentCommand) -> UUID:
        try:
            return UUID(command.intent_id)
        except ValueError:
            self._reject(command, "intent_not_found", None)
            raise PaymentIntentNotFoundError from None

    def _ensure_refundable(
        self, intent: PaymentIntent, amount: Amount, command: RefundPaymentCommand
    ) -> None:
        if not intent.can_be_refunded():
            self._reject(command, f"status_{intent.status.value}", str(intent.id), intent)
            raise IntentNotRefundableError
        if amount.cents > intent.refundable_cents:
            self._reject(
                command,
                "amount_exceeds_refundable",
                str(intent.id),
                intent,
                {"requested_cents": amount.cents, "refundable_cents": intent.refundable_cents},
            )
            raise RefundExceedsCapturedError

    def _replay(
        self,
        record: Refund,
        intent: PaymentIntent,
        fingerprint: str,
        command: RefundPaymentCommand,
    ) -> RefundView:
        if record.request_hash != fingerprint:
            self._reject(command, "idempotency_key_reused", str(intent.id), intent)
            raise RefundKeyReusedError
        return RefundView.from_entities(record, intent, replayed=True)

    def _log_refund(
        self,
        command: RefundPaymentCommand,
        refund: Refund,
        refunded: PaymentIntent,
        ledger: LedgerTransaction,
    ) -> None:
        self._events.log(
            BusinessEvent.success(
                names.REFUND_SUCCEEDED,
                resource_type="refund",
                resource_id=str(refund.id),
                actor_type="service",
                actor_id=command.caller,
                attributes={
                    "payment_intent_id": str(refunded.id),
                    "order_reference": refunded.order_reference,
                    "amount_cents": refund.amount.cents,
                    "amount_refunded_cents": refunded.refunded_amount,
                    "currency": refunded.currency.value,
                },
            )
        )
        written: dict[str, Scalar] = {
            "transaction_id": str(ledger.id),
            "entry_count": len(ledger.entries),
            "amount_cents": refund.amount.cents,
        }
        self._events.log(
            BusinessEvent.success(
                names.LEDGER_ENTRIES_WRITTEN, **self._fields(command, str(refunded.id), written)
            )
        )

    def _log_queued(self, outbox_event: OutboxEvent) -> None:
        self._events.log(
            BusinessEvent.success(
                webhook_names.WEBHOOK_EVENT_QUEUED,
                resource_type="webhook_event",
                resource_id=str(outbox_event.id),
                attributes={
                    "event_type": outbox_event.event_type.value,
                    "payment_intent_id": str(outbox_event.intent_id),
                },
            )
        )

    def _reject(
        self,
        command: RefundPaymentCommand,
        reason: str,
        intent_id: str | None,
        intent: PaymentIntent | None = None,
        extra: Mapping[str, Scalar] | None = None,
    ) -> None:
        attributes: dict[str, Scalar] = {}
        if intent:
            attributes = {
                "order_reference": intent.order_reference,
                "currency": intent.currency.value,
            }
        attributes.update(extra or {})
        self._events.log(
            BusinessEvent.denied(
                names.REFUND_REJECTED, reason, **self._fields(command, intent_id, attributes)
            )
        )

    @staticmethod
    def _fields(
        command: RefundPaymentCommand, intent_id: str | None, attributes: Mapping[str, Scalar]
    ) -> dict[str, object]:
        """Ressource et acteur de l'événement : jamais la clé d'idempotence ni la valeur reçue."""
        return {
            "resource_type": "payment_intent",
            "resource_id": intent_id,
            "actor_type": "service",
            "actor_id": command.caller,
            "attributes": attributes,
        }
