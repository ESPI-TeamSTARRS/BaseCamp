from app.order.domain.enums.order_status import OrderStatus
from app.payment_confirmation.application.applied_event import AppliedEvent
from app.payment_confirmation.application.payment_webhook_events import CURRENCY
from app.payment_confirmation.domain.entities.payment_event import PaymentEvent
from app.payment_confirmation.domain.entities.settlement_target import SettlementTarget
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.interfaces.confirmation_unit_of_work import (
    ConfirmationUnitOfWork,
)
from app.payment_request.domain.entities.payment_attempt import (
    FAILED,
    REQUIRES_CONFIRMATION,
    SUCCEEDED,
)

PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_FAILED = "payment.failed"
REFUND_SUCCEEDED = "refund.succeeded"


class ApplyPaymentEvent:
    """Applique un événement authentifié dans la transaction en cours; ne valide rien lui-même.

    Point d'extension : un nouveau type d'événement s'ajoute dans `apply`.
    """

    def apply(self, uow: ConfirmationUnitOfWork, event: PaymentEvent) -> AppliedEvent:
        if event.event_type == PAYMENT_SUCCEEDED:
            return self._succeeded(uow, event)
        if event.event_type == PAYMENT_FAILED:
            return self._failed(uow, event)
        if event.event_type == REFUND_SUCCEEDED:
            return self._refunded(uow, event)
        return AppliedEvent(WebhookOutcome.IGNORED, "unsupported_type")

    def _target(self, uow: ConfirmationUnitOfWork, event: PaymentEvent) -> SettlementTarget | None:
        if event.reference is None:
            return None
        return uow.targets.find_for_update(event.reference)

    def _succeeded(self, uow: ConfirmationUnitOfWork, event: PaymentEvent) -> AppliedEvent:
        target = self._target(uow, event)
        if target is None:
            return AppliedEvent(WebhookOutcome.IGNORED, "order_not_found")
        refusal = self._refusal(uow, event, target)
        if refusal is not None:
            return AppliedEvent(
                WebhookOutcome.IGNORED, refusal, target.order_id, target.order_number
            )
        if target.order_status is OrderStatus.PENDING_PAYMENT:
            uow.targets.mark_paid(target.order_id)
        uow.targets.set_attempt_status(target.attempt_id, SUCCEEDED)
        uow.targets.commit_reservations(target.order_id)
        return AppliedEvent(
            WebhookOutcome.APPLIED,
            None,
            target.order_id,
            target.order_number,
            confirmed=True,
            mail=uow.targets.mail_for(target.order_id),
        )

    def _refusal(
        self, uow: ConfirmationUnitOfWork, event: PaymentEvent, target: SettlementTarget
    ) -> str | None:
        """Pourquoi l'événement ne doit pas payer la commande (jamais un montant ou une devise douteux)."""
        if event.amount_cents != target.total_cents:
            return "amount_mismatch"
        if event.currency != CURRENCY:
            return "currency_mismatch"
        if target.order_status is OrderStatus.EXPIRED:
            return "order_expired"
        if uow.events.is_order_confirmed(target.order_id):
            return "order_already_confirmed"
        return None

    def _failed(self, uow: ConfirmationUnitOfWork, event: PaymentEvent) -> AppliedEvent:
        target = self._target(uow, event)
        if target is None:
            return AppliedEvent(WebhookOutcome.IGNORED, "order_not_found")
        if target.attempt_status == SUCCEEDED:
            return AppliedEvent(
                WebhookOutcome.IGNORED, "attempt_settled", target.order_id, target.order_number
            )
        if target.attempt_status == REQUIRES_CONFIRMATION:
            uow.targets.set_attempt_status(target.attempt_id, FAILED)
        return AppliedEvent(WebhookOutcome.APPLIED, None, target.order_id, target.order_number)

    def _refunded(self, uow: ConfirmationUnitOfWork, event: PaymentEvent) -> AppliedEvent:
        """Le cumul remboursé ne fait que croître : un rejeu ou un événement plus ancien est ignoré."""
        target = self._target(uow, event)
        if target is None:
            return AppliedEvent(WebhookOutcome.IGNORED, "order_not_found")
        refunded = event.amount_refunded_cents
        reason = self._refund_refusal(target, refunded)
        if reason is not None or refunded is None:
            return AppliedEvent(
                WebhookOutcome.IGNORED, reason, target.order_id, target.order_number
            )
        uow.targets.record_refund(target.order_id, refunded)
        return AppliedEvent(
            WebhookOutcome.APPLIED,
            None,
            target.order_id,
            target.order_number,
            refunded_cents=refunded,
        )

    @staticmethod
    def _refund_refusal(target: SettlementTarget, refunded: int | None) -> str | None:
        if refunded is None:
            return "refund_amount_missing"
        if target.order_status is not OrderStatus.PAID:
            return "order_not_paid"
        if refunded > target.total_cents:
            return "refund_exceeds_total"
        if refunded <= target.refunded_cents:
            return "refund_already_recorded"
        return None
