from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
SETTLED = [
    IntentStatus.SUCCEEDED,
    IntentStatus.FAILED,
    IntentStatus.CANCELED,
    IntentStatus.EXPIRED,
]


def _intent() -> PaymentIntent:
    return PaymentIntent.create("CMD-1", Amount(2500), Currency.EUR, NOW, timedelta(minutes=30))


class TestCancellationAndExpiryTransitions:
    def test_cancel_returns_a_canceled_copy(self) -> None:
        intent = _intent()

        assert intent.cancel().status is IntentStatus.CANCELED
        assert intent.status is IntentStatus.REQUIRES_CONFIRMATION

    def test_expire_returns_an_expired_copy(self) -> None:
        assert _intent().expire().status is IntentStatus.EXPIRED

    def test_an_intent_is_overdue_from_its_deadline_on(self) -> None:
        intent = _intent()

        assert not intent.is_overdue(NOW + timedelta(minutes=29, seconds=59))
        assert intent.is_overdue(NOW + timedelta(minutes=30))

    def test_an_unconfirmed_intent_can_be_canceled_before_its_deadline(self) -> None:
        assert _intent().can_be_canceled(NOW + timedelta(minutes=29))

    @pytest.mark.parametrize("status", SETTLED)
    def test_an_intent_outside_requires_confirmation_cannot_be_canceled(
        self, status: IntentStatus
    ) -> None:
        assert not replace(_intent(), status=status).can_be_canceled(NOW)

    def test_an_overdue_intent_can_no_longer_be_canceled(self) -> None:
        assert not _intent().can_be_canceled(NOW + timedelta(minutes=30))
