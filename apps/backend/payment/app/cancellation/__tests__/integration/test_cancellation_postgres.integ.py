"""Concurrence annulation / confirmation sur Postgres : une intention confirmée ne s'annule plus
et inversement. Le verrou de ligne (`SELECT … FOR UPDATE`) départage, même entre deux instances.
"""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from app.cancellation.application.cancel_payment_intent import CancelPaymentIntentUseCase
from app.cancellation.application.commands.cancel_payment_command import CancelPaymentCommand
from app.cancellation.domain.exceptions.intent_not_cancelable_error import (
    IntentNotCancelableError,
)
from app.cancellation.infrastructure.repositories.sqlalchemy_cancellation_unit_of_work import (
    SqlAlchemyCancellationUnitOfWork,
)
from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.application.confirm_payment import ConfirmPaymentUseCase
from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.exceptions.intent_not_confirmable_error import (
    IntentNotConfirmableError,
)
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.__tests__.postgres_support import (
    add_intent,
    count_ledger_entries,
    migrated_engine,
    requires_postgres,
)
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.value_objects.amount import Amount

pytestmark = requires_postgres


class ApprovingProvider(PaymentProvider):
    """Signale `entered` dès qu'il est appelé : l'intention est alors verrouillée par la confirmation."""

    def __init__(self, delay: float = 0.0, entered: threading.Event | None = None) -> None:
        self._delay = delay
        self.entered = entered or threading.Event()

    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome:
        self.entered.set()
        time.sleep(self._delay)
        return ProviderOutcome.APPROVED


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    yield from migrated_engine(monkeypatch)


def _confirm(
    engine: Engine, intent: PaymentIntent, provider: ApprovingProvider | None = None
) -> None:
    ConfirmPaymentUseCase(
        SqlAlchemyConfirmationUnitOfWork(engine),
        provider or ApprovingProvider(),
        lambda: datetime.now(UTC),
        InMemoryBusinessEventLogger(),
    ).execute(ConfirmPaymentCommand("shop", "confirm-key-0001", str(intent.id), "pm_test_success"))


def _cancel(engine: Engine, intent: PaymentIntent) -> None:
    CancelPaymentIntentUseCase(
        SqlAlchemyCancellationUnitOfWork(engine),
        lambda: datetime.now(UTC),
        InMemoryBusinessEventLogger(),
    ).execute(CancelPaymentCommand("shop", str(intent.id)))


def _status(engine: Engine, intent: PaymentIntent) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT status FROM payment_intents WHERE id = :id"), {"id": intent.id}
            ).scalar_one()
        )


def _race(first: Callable[[], None], second: Callable[[], None]) -> list[str]:
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt(action: Callable[[], None]) -> None:
        barrier.wait()
        try:
            action()
            outcomes.append("ok")
        except (IntentNotConfirmableError, IntentNotCancelableError):
            outcomes.append("conflict")

    threads = [threading.Thread(target=attempt, args=(action,)) for action in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes


class TestCancelVersusConfirm:
    def test_a_confirmation_in_progress_wins_and_the_cancellation_is_refused(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine)
        provider = ApprovingProvider(delay=0.5)
        confirming = threading.Thread(target=_confirm, args=(engine, intent, provider))
        confirming.start()
        assert provider.entered.wait(10)  # la confirmation tient le verrou pendant l'appel

        with pytest.raises(IntentNotCancelableError):
            _cancel(engine, intent)

        confirming.join()
        assert _status(engine, intent) == "succeeded"
        assert count_ledger_entries(engine) == 2

    def test_a_cancellation_wins_and_the_confirmation_is_refused(self, engine: Engine) -> None:
        intent = add_intent(engine)
        _cancel(engine, intent)

        with pytest.raises(IntentNotConfirmableError):
            _confirm(engine, intent)

        assert _status(engine, intent) == "canceled"
        assert count_ledger_entries(engine) == 0

    @pytest.mark.parametrize("attempt", range(5))
    def test_a_simultaneous_cancel_and_confirm_never_both_succeed(
        self, engine: Engine, attempt: int
    ) -> None:
        intent = add_intent(engine)

        outcomes = _race(lambda: _confirm(engine, intent), lambda: _cancel(engine, intent))

        assert sorted(outcomes) == ["conflict", "ok"]
        status = _status(engine, intent)
        assert status in {"succeeded", "canceled"}
        assert count_ledger_entries(engine) == (2 if status == "succeeded" else 0)

    def test_two_simultaneous_cancellations_both_end_canceled(self, engine: Engine) -> None:
        intent = add_intent(engine)

        outcomes = _race(lambda: _cancel(engine, intent), lambda: _cancel(engine, intent))

        assert outcomes == ["ok", "ok"]
        assert _status(engine, intent) == "canceled"
