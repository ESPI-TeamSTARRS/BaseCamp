from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
TTL = timedelta(minutes=30)


class TestPaymentIntent:
    def test_new_intent_requires_confirmation_and_expires_after_the_ttl(self) -> None:
        intent = PaymentIntent.create("CMD-1", Amount(2500), Currency.EUR, NOW, TTL)

        assert isinstance(intent.id, UUID)
        assert intent.status is IntentStatus.REQUIRES_CONFIRMATION
        assert intent.refunded_amount == 0
        assert intent.expires_at == NOW + TTL
        assert intent.created_at == NOW

    def test_each_intent_gets_its_own_id(self) -> None:
        first = PaymentIntent.create("A", Amount(1), Currency.EUR, NOW, TTL)
        second = PaymentIntent.create("B", Amount(1), Currency.EUR, NOW, TTL)

        assert first.id != second.id
