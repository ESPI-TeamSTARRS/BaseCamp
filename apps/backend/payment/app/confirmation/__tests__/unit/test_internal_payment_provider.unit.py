from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.infrastructure.providers.internal_payment_provider import (
    InternalPaymentProvider,
)
from app.intent.domain.value_objects.amount import Amount


class TestInternalPaymentProvider:
    def test_the_success_method_is_approved_without_waiting(self) -> None:
        waits: list[float] = []

        outcome = InternalPaymentProvider(waits.append, 2.0).authorize(
            PaymentMethod.SUCCESS, Amount(100)
        )

        assert outcome is ProviderOutcome.APPROVED
        assert waits == []

    def test_the_declined_method_is_declined_without_waiting(self) -> None:
        waits: list[float] = []

        outcome = InternalPaymentProvider(waits.append, 2.0).authorize(
            PaymentMethod.DECLINED, Amount(100)
        )

        assert outcome is ProviderOutcome.DECLINED
        assert waits == []

    def test_the_timeout_method_waits_for_the_bounded_delay_then_times_out(self) -> None:
        waits: list[float] = []

        outcome = InternalPaymentProvider(waits.append, 1.5).authorize(
            PaymentMethod.TIMEOUT, Amount(100)
        )

        assert outcome is ProviderOutcome.TIMED_OUT
        assert waits == [1.5]
