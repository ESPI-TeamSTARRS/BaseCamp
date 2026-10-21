from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

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


class TestConfirmationTransitions:
    @staticmethod
    def _intent(status: IntentStatus = IntentStatus.REQUIRES_CONFIRMATION) -> PaymentIntent:
        created = PaymentIntent.create(
            "CMD-1", Amount(2500), Currency.EUR, NOW, timedelta(minutes=30)
        )
        return replace(created, status=status)

    def test_a_fresh_intent_can_be_confirmed_before_its_expiry(self) -> None:
        assert self._intent().can_be_confirmed(NOW + timedelta(minutes=29))

    def test_an_expired_intent_cannot_be_confirmed(self) -> None:
        assert not self._intent().can_be_confirmed(NOW + timedelta(minutes=30))

    @pytest.mark.parametrize(
        "status",
        [IntentStatus.SUCCEEDED, IntentStatus.FAILED, IntentStatus.CANCELED, IntentStatus.EXPIRED],
    )
    def test_an_intent_outside_requires_confirmation_cannot_be_confirmed(
        self, status: IntentStatus
    ) -> None:
        assert not self._intent(status).can_be_confirmed(NOW)

    def test_succeed_returns_a_succeeded_copy(self) -> None:
        intent = self._intent()

        assert intent.succeed().status is IntentStatus.SUCCEEDED
        assert intent.status is IntentStatus.REQUIRES_CONFIRMATION

    def test_fail_returns_a_failed_copy(self) -> None:
        assert self._intent().fail().status is IntentStatus.FAILED
