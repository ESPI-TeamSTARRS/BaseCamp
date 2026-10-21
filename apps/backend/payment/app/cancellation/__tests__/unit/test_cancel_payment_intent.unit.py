from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.cancellation.application import cancellation_event_names as names
from app.cancellation.application.cancel_payment_intent import CancelPaymentIntentUseCase
from app.cancellation.application.commands.cancel_payment_command import CancelPaymentCommand
from app.cancellation.domain.exceptions.intent_not_cancelable_error import (
    IntentNotCancelableError,
)
from app.cancellation.domain.interfaces.cancellation_session import CancellationSession
from app.cancellation.domain.interfaces.cancellation_unit_of_work import CancellationUnitOfWork
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.value_objects.amount import Amount

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


class InMemorySession(CancellationSession):
    def __init__(self, intents: dict[UUID, PaymentIntent]) -> None:
        self._intents = intents

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        return self._intents.get(intent_id)

    def save(self, intent: PaymentIntent) -> None:
        self._intents[intent.id] = intent


class InMemoryUnitOfWork(CancellationUnitOfWork):
    def __init__(self, intents: dict[UUID, PaymentIntent]) -> None:
        self._intents = intents

    @contextmanager
    def begin(self) -> Iterator[CancellationSession]:
        yield InMemorySession(self._intents)


class Fixture:
    def __init__(self) -> None:
        self.intent = PaymentIntent.create(
            "CMD-1", Amount(4990), Currency.EUR, NOW - timedelta(minutes=1), timedelta(minutes=30)
        )
        self.intents = {self.intent.id: self.intent}
        self.logger = InMemoryBusinessEventLogger()
        self.use_case = CancelPaymentIntentUseCase(
            InMemoryUnitOfWork(self.intents), lambda: NOW, self.logger
        )

    def with_status(self, status: IntentStatus) -> None:
        self.intent = replace(self.intent, status=status)
        self.intents[self.intent.id] = self.intent

    def command(self, **overrides: object) -> CancelPaymentCommand:
        values: dict[str, object] = {"caller": "shop", "intent_id": str(self.intent.id)}
        values.update(overrides)
        return CancelPaymentCommand(**values)  # type: ignore[arg-type]

    def summary(self) -> list[tuple[str, Outcome, str | None]]:
        return [(e.event, e.outcome, e.reason) for e in self.logger.events]


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


class TestCancellation:
    def test_an_unconfirmed_intent_becomes_canceled(self, fx: Fixture) -> None:
        view = fx.use_case.execute(fx.command())

        assert view.status == "canceled"
        assert view.id == str(fx.intent.id)
        assert fx.intents[fx.intent.id].status is IntentStatus.CANCELED

    def test_canceling_twice_is_idempotent_and_emits_nothing_new(self, fx: Fixture) -> None:
        first = fx.use_case.execute(fx.command())
        fx.logger.events.clear()

        second = fx.use_case.execute(fx.command())

        assert second == first
        assert fx.logger.events == []

    @pytest.mark.parametrize(
        "status", [IntentStatus.SUCCEEDED, IntentStatus.FAILED, IntentStatus.EXPIRED]
    )
    def test_an_intent_already_settled_or_expired_cannot_be_canceled(
        self, fx: Fixture, status: IntentStatus
    ) -> None:
        fx.with_status(status)

        with pytest.raises(IntentNotCancelableError):
            fx.use_case.execute(fx.command())

        assert fx.intents[fx.intent.id].status is status

    def test_an_overdue_intent_cannot_be_canceled(self, fx: Fixture) -> None:
        fx.intents[fx.intent.id] = replace(fx.intent, expires_at=NOW)

        with pytest.raises(IntentNotCancelableError):
            fx.use_case.execute(fx.command())

        assert fx.intents[fx.intent.id].status is IntentStatus.REQUIRES_CONFIRMATION

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_an_unknown_or_malformed_intent_is_not_found(self, fx: Fixture, intent_id: str) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.execute(fx.command(intent_id=intent_id))


class TestBusinessEvents:
    def test_a_cancellation_logs_payment_canceled_with_the_intent_details(
        self, fx: Fixture
    ) -> None:
        fx.use_case.execute(fx.command())

        assert fx.summary() == [(names.PAYMENT_CANCELED, Outcome.SUCCESS, None)]
        (event,) = fx.logger.events
        assert (event.resource_type, event.resource_id) == ("payment_intent", str(fx.intent.id))
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert event.attributes == {
            "order_reference": "CMD-1",
            "amount_cents": 4990,
            "currency": "EUR",
        }

    def test_a_succeeded_intent_is_rejected_with_its_status(self, fx: Fixture) -> None:
        fx.with_status(IntentStatus.SUCCEEDED)

        with pytest.raises(IntentNotCancelableError):
            fx.use_case.execute(fx.command())

        assert fx.summary() == [
            (names.PAYMENT_CANCELLATION_REJECTED, Outcome.DENIED, "status_succeeded")
        ]

    def test_an_overdue_intent_is_rejected_as_expired(self, fx: Fixture) -> None:
        fx.intents[fx.intent.id] = replace(fx.intent, expires_at=NOW)

        with pytest.raises(IntentNotCancelableError):
            fx.use_case.execute(fx.command())

        assert fx.summary() == [(names.PAYMENT_CANCELLATION_REJECTED, Outcome.DENIED, "expired")]

    def test_an_unknown_intent_is_rejected_without_echoing_the_received_id(
        self, fx: Fixture
    ) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.execute(fx.command(intent_id="4242424242424242"))

        (event,) = fx.logger.events
        assert (event.event, event.reason) == (
            names.PAYMENT_CANCELLATION_REJECTED,
            "intent_not_found",
        )
        assert event.resource_id is None
        assert "4242" not in repr(event)
