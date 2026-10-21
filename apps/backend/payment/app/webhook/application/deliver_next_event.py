from collections.abc import Callable
from datetime import datetime

from app.core.events.business_event import BusinessEvent, Scalar
from app.core.events.business_event_logger import BusinessEventLogger
from app.webhook.application import webhook_event_names as names
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.interfaces.delivery_unit_of_work import DeliveryUnitOfWork
from app.webhook.domain.interfaces.expired_order_refunder import ExpiredOrderRefunder
from app.webhook.domain.interfaces.webhook_sender import WebhookSender
from app.webhook.domain.services.webhook_signer import WebhookSigner
from app.webhook.domain.value_objects.delivery_result import DeliveryResult
from app.webhook.domain.value_objects.retry_policy import RetryPolicy


class DeliverNextEventUseCase:
    """Livre le plus ancien événement échu, une tentative à la fois.

    L'événement est verrouillé (ligne) pendant l'envoi : deux workers ne livrent jamais le même.
    Chaque tentative est signée avec l'horodatage du moment (la fenêtre de ± 5 min du récepteur
    reste respectée après des heures d'attente) mais envoie le même identifiant et le même corps.
    Un échec reprogramme l'événement; au-delà du budget il passe `dead` et une erreur est journalisée.
    Les événements ne sont journalisés qu'après la validation de la transaction.
    """

    def __init__(
        self,
        unit_of_work: DeliveryUnitOfWork,
        sender: WebhookSender,
        signer: WebhookSigner,
        policy: RetryPolicy,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
        refunder: ExpiredOrderRefunder | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._sender = sender
        self._signer = signer
        self._policy = policy
        self._clock = clock
        self._events = events
        self._refunder = refunder

    def execute(self) -> bool:
        """Vrai si un événement échu a été traité (livré ou reprogrammé), faux s'il n'y en a pas."""
        with self._unit_of_work.begin() as session:
            event = session.claim_next_due(self._clock())
            if event is None:
                return False
            header = self._signer.header(int(self._clock().timestamp()), event.body)
            result = self._sender.send(event.id, event.body, header)
            now = self._clock()
            settled = self._settle(event, result, now)
            session.save(settled)
        self._log(settled, result.status_code)
        return True

    def _settle(self, event: OutboxEvent, result: DeliveryResult, now: datetime) -> OutboxEvent:
        if result.delivered:
            return event.mark_delivered(now)
        reason = result.reason or "unknown_error"
        if result.rejected and self._refunder is not None and self._is_refundable(event):
            try:
                self._refunder.refund_in_full(event)
            except Exception:
                return event.mark_failed(now, "auto_refund_failed", self._policy)
            return event.mark_rejected(now, reason)
        return event.mark_failed(now, reason, self._policy)

    @staticmethod
    def _is_refundable(event: OutboxEvent) -> bool:
        """Seul un paiement réussi refusé par la boutique se rembourse (jamais un échec ni un remboursement)."""
        return event.event_type is WebhookEventType.PAYMENT_SUCCEEDED

    def _log(self, event: OutboxEvent, status_code: int | None) -> None:
        resource = {"resource_type": "webhook_event", "resource_id": str(event.id)}
        common: dict[str, Scalar] = {
            "event_type": event.event_type.value,
            "payment_intent_id": str(event.intent_id),
        }
        if event.status is OutboxStatus.DELIVERED:
            attributes = {**common, "attempt": event.attempts, "status_code": status_code}
            self._events.log(
                BusinessEvent.success(names.WEBHOOK_DELIVERED, attributes=attributes, **resource)
            )
        elif event.status is OutboxStatus.REJECTED_BY_RECEIVER:
            attributes = {**common, "attempt": event.attempts, "status_code": status_code}
            self._events.log(
                BusinessEvent.error(
                    names.WEBHOOK_REJECTED_BY_RECEIVER,
                    event.last_error or "rejected_by_receiver",
                    attributes=attributes,
                    **resource,
                )
            )
        elif event.status is OutboxStatus.DEAD:
            attributes = {**common, "attempts": event.attempts, "last_error": event.last_error}
            self._events.log(
                BusinessEvent.error(
                    names.WEBHOOK_EVENT_DEAD,
                    "max_attempts_reached",
                    attributes=attributes,
                    **resource,
                )
            )
        else:
            retry_in = int((event.next_attempt_at - self._clock()).total_seconds())
            attributes = {
                **common,
                "attempt": event.attempts,
                "status_code": status_code,
                "retry_in_seconds": retry_in,
            }
            self._events.log(
                BusinessEvent.error(
                    names.WEBHOOK_DELIVERY_FAILED,
                    event.last_error or "unknown_error",
                    attributes=attributes,
                    **resource,
                )
            )
