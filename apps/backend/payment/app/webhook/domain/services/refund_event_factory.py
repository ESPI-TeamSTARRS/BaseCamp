import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.value_objects.amount import Amount
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.webhook_event_type import WebhookEventType


class RefundEventFactory:
    """Construit l'événement `refund.succeeded` publié à la boutique pour un remboursement émis.

    `intent` est l'intention après le remboursement : `amount_refunded` est le cumul rendu à cet
    instant. Même format compact que les événements de paiement (ces octets sont signés), jamais
    de donnée de carte, de jeton ni de secret.
    """

    def __init__(self, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def build(
        self, intent: PaymentIntent, refund_id: UUID, amount: Amount, now: datetime
    ) -> OutboxEvent:
        event_id = self._id_factory()
        body = json.dumps(
            {
                "id": str(event_id),
                "type": WebhookEventType.REFUND_SUCCEEDED.value,
                "created_at": now.astimezone(UTC).isoformat(timespec="milliseconds")[:-6] + "Z",
                "data": {
                    "refund_id": str(refund_id),
                    "payment_intent_id": str(intent.id),
                    "order_reference": intent.order_reference,
                    "amount": amount.cents,
                    "amount_refunded": intent.refunded_amount,
                    "currency": intent.currency.value,
                    "status": "succeeded",
                },
            },
            separators=(",", ":"),
        )
        return OutboxEvent.pending(
            event_id, WebhookEventType.REFUND_SUCCEEDED, intent.id, body, now
        )
