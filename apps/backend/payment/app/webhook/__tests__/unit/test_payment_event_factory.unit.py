import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.payment_event_factory import PaymentEventFactory

NOW = datetime(2026, 10, 21, 9, 0, 0, 123000, tzinfo=UTC)
EVENT_ID = UUID("0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11")


def _intent() -> PaymentIntent:
    return PaymentIntent.create(
        "CMD-2026-0001", Amount(4990), Currency.EUR, NOW, timedelta(minutes=30)
    )


class TestPaymentEventFactory:
    def test_a_succeeded_intent_gives_a_payment_succeeded_event(self) -> None:
        intent = _intent().succeed()

        event = PaymentEventFactory(lambda: EVENT_ID).build(intent, NOW)

        assert event.id == EVENT_ID
        assert event.event_type is WebhookEventType.PAYMENT_SUCCEEDED
        assert event.intent_id == intent.id
        assert event.status is OutboxStatus.PENDING

    def test_a_failed_intent_gives_a_payment_failed_event(self) -> None:
        event = PaymentEventFactory(lambda: EVENT_ID).build(_intent().fail(), NOW)

        assert event.event_type is WebhookEventType.PAYMENT_FAILED

    def test_the_published_body_has_a_stable_documented_shape(self) -> None:
        intent = _intent().succeed()

        body = PaymentEventFactory(lambda: EVENT_ID).build(intent, NOW).body

        assert json.loads(body) == {
            "id": str(EVENT_ID),
            "type": "payment.succeeded",
            "created_at": "2026-10-21T09:00:00.123Z",
            "data": {
                "payment_intent_id": str(intent.id),
                "order_reference": "CMD-2026-0001",
                "amount": 4990,
                "currency": "EUR",
                "status": "succeeded",
            },
        }

    def test_the_body_is_compact_so_the_signed_bytes_are_unambiguous(self) -> None:
        body = PaymentEventFactory(lambda: EVENT_ID).build(_intent().succeed(), NOW).body

        assert ", " not in body
        assert ": " not in body

    def test_an_intent_that_has_not_settled_has_no_event(self) -> None:
        with pytest.raises(ValueError, match="settled"):
            PaymentEventFactory(lambda: EVENT_ID).build(_intent(), NOW)

    def test_each_event_gets_its_own_id_by_default(self) -> None:
        factory = PaymentEventFactory()
        intent = _intent().succeed()

        assert factory.build(intent, NOW).id != factory.build(intent, NOW).id
