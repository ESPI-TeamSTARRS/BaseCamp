import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.refund_event_factory import RefundEventFactory

NOW = datetime(2026, 10, 21, 9, 0, 0, 123000, tzinfo=UTC)
EVENT_ID = UUID("0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11")
REFUND_ID = UUID("5c1c4b52-96a6-4d52-8f0b-6b0e1b2f7a33")


def _refunded_intent() -> PaymentIntent:
    created = PaymentIntent.create(
        "CMD-2026-0001", Amount(10000), Currency.EUR, NOW, timedelta(minutes=30)
    )
    return created.succeed().refund(Amount(4000))


class TestRefundEventFactory:
    def test_a_refund_gives_a_pending_refund_succeeded_event(self) -> None:
        intent = _refunded_intent()

        event = RefundEventFactory(lambda: EVENT_ID).build(intent, REFUND_ID, Amount(4000), NOW)

        assert event.id == EVENT_ID
        assert event.event_type is WebhookEventType.REFUND_SUCCEEDED
        assert event.event_type.value == "refund.succeeded"
        assert event.intent_id == intent.id
        assert event.status is OutboxStatus.PENDING

    def test_the_published_body_has_a_stable_documented_shape(self) -> None:
        intent = _refunded_intent()

        body = RefundEventFactory(lambda: EVENT_ID).build(intent, REFUND_ID, Amount(4000), NOW).body

        assert json.loads(body) == {
            "id": str(EVENT_ID),
            "type": "refund.succeeded",
            "created_at": "2026-10-21T09:00:00.123Z",
            "data": {
                "refund_id": str(REFUND_ID),
                "payment_intent_id": str(intent.id),
                "order_reference": "CMD-2026-0001",
                "amount": 4000,
                "amount_refunded": 4000,
                "currency": "EUR",
                "status": "succeeded",
            },
        }

    def test_the_body_is_compact_so_the_signed_bytes_are_unambiguous(self) -> None:
        body = (
            RefundEventFactory(lambda: EVENT_ID)
            .build(_refunded_intent(), REFUND_ID, Amount(4000), NOW)
            .body
        )

        assert ", " not in body
        assert ": " not in body

    def test_each_event_gets_its_own_id_by_default(self) -> None:
        factory = RefundEventFactory()
        intent = _refunded_intent()

        first = factory.build(intent, REFUND_ID, Amount(4000), NOW)
        second = factory.build(intent, REFUND_ID, Amount(4000), NOW)

        assert first.id != second.id
