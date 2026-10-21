import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.intent_status import IntentStatus
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.webhook_event_type import WebhookEventType

_TYPE_BY_STATUS = {
    IntentStatus.SUCCEEDED: WebhookEventType.PAYMENT_SUCCEEDED,
    IntentStatus.FAILED: WebhookEventType.PAYMENT_FAILED,
}


class PaymentEventFactory:
    """Construit l'événement publié à la boutique pour une intention qui vient d'être réglée.

    Format publié (docs/services/payment.md) : jamais de donnée de carte, de jeton ni de secret.
    Le corps est du JSON compact : ce sont ces octets-là qui sont signés puis envoyés.
    """

    def __init__(self, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def build(self, intent: PaymentIntent, now: datetime) -> OutboxEvent:
        event_type = _TYPE_BY_STATUS.get(intent.status)
        if event_type is None:
            raise ValueError("only a settled intent (succeeded or failed) has an event")
        event_id = self._id_factory()
        body = json.dumps(
            {
                "id": str(event_id),
                "type": event_type.value,
                "created_at": now.astimezone(UTC).isoformat(timespec="milliseconds")[:-6] + "Z",
                "data": {
                    "payment_intent_id": str(intent.id),
                    "order_reference": intent.order_reference,
                    "amount": intent.amount.cents,
                    "currency": intent.currency.value,
                    "status": intent.status.value,
                },
            },
            separators=(",", ":"),
        )
        return OutboxEvent.pending(event_id, event_type, intent.id, body, now)
