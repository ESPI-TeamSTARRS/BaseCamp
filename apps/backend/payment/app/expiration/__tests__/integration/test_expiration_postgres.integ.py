"""Expiration sur Postgres : verrous de ligne, passages concurrents et migration additive 0005."""

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.cancellation.application.cancel_payment_intent import CancelPaymentIntentUseCase
from app.cancellation.application.commands.cancel_payment_command import CancelPaymentCommand
from app.cancellation.infrastructure.repositories.sqlalchemy_cancellation_unit_of_work import (
    SqlAlchemyCancellationUnitOfWork,
)
from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.application.confirm_payment import ConfirmPaymentUseCase
from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.__tests__.postgres_support import (
    add_intent,
    alembic_config,
    count_ledger_entries,
    migrated_engine,
    requires_postgres,
)
from app.expiration.application.expire_unconfirmed_intents import ExpireUnconfirmedIntentsUseCase
from app.expiration.infrastructure.repositories.sqlalchemy_intent_expiry_repository import (
    SqlAlchemyIntentExpiryRepository,
)
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.value_objects.amount import Amount

pytestmark = requires_postgres

LONG_AGO = datetime.now(UTC) - timedelta(hours=2)


class SlowApprovingProvider(PaymentProvider):
    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome:
        time.sleep(0.5)
        return ProviderOutcome.APPROVED


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    yield from migrated_engine(monkeypatch)


def _expire(engine: Engine, events: InMemoryBusinessEventLogger | None = None) -> int:
    return (
        ExpireUnconfirmedIntentsUseCase(
            SqlAlchemyIntentExpiryRepository(engine),
            lambda: datetime.now(UTC),
            batch_size=3,
            events=events or InMemoryBusinessEventLogger(),
        )
        .execute()
        .expired_count
    )


def _status(engine: Engine, intent: PaymentIntent) -> str:
    with engine.connect() as connection:
        return str(
            connection.execute(
                text("SELECT status FROM payment_intents WHERE id = :id"), {"id": intent.id}
            ).scalar_one()
        )


class TestExpirationOnPostgres:
    def test_only_overdue_unconfirmed_intents_expire_and_no_ledger_entry_is_written(
        self, engine: Engine
    ) -> None:
        overdue = [add_intent(engine, LONG_AGO) for _ in range(7)]
        fresh = add_intent(engine)

        assert _expire(engine) == 7

        assert {_status(engine, i) for i in overdue} == {"expired"}
        assert _status(engine, fresh) == "requires_confirmation"
        assert count_ledger_entries(engine) == 0

    def test_a_second_run_has_no_second_effect(self, engine: Engine) -> None:
        add_intent(engine, LONG_AGO)
        _expire(engine)
        events = InMemoryBusinessEventLogger()

        assert _expire(engine, events) == 0
        assert events.events == []

    def test_a_row_locked_by_another_transaction_is_skipped_then_taken_next_time(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine, LONG_AGO)
        with Session(engine) as holder:
            holder.execute(
                text("SELECT id FROM payment_intents WHERE id = :id FOR UPDATE"), {"id": intent.id}
            )

            assert _expire(engine) == 0
            assert _status(engine, intent) == "requires_confirmation"

        assert _expire(engine) == 1
        assert _status(engine, intent) == "expired"

    def test_two_simultaneous_runs_expire_each_intent_exactly_once(self, engine: Engine) -> None:
        for _ in range(9):
            add_intent(engine, LONG_AGO)
        barrier = threading.Barrier(2)
        totals: list[int] = []

        def run() -> None:
            barrier.wait()
            totals.append(_expire(engine))

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sum(totals) == 9

    def test_a_confirmation_in_progress_is_not_overwritten_by_the_expiration(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine, datetime.now(UTC) - timedelta(minutes=29, seconds=59))
        confirmation = ConfirmPaymentUseCase(
            SqlAlchemyConfirmationUnitOfWork(engine),
            SlowApprovingProvider(),
            lambda: datetime.now(UTC),
            InMemoryBusinessEventLogger(),
        )
        confirming = threading.Thread(
            target=confirmation.execute,
            args=(
                ConfirmPaymentCommand(
                    "shop", "confirm-key-0001", str(intent.id), "pm_test_success"
                ),
            ),
        )
        confirming.start()
        time.sleep(0.2)  # l'échéance est passée pendant que la confirmation tient le verrou

        expired = _expire(engine)
        confirming.join()

        assert expired == 0
        assert _status(engine, intent) == "succeeded"
        assert count_ledger_entries(engine) == 2

    def test_a_cancellation_in_progress_is_not_overwritten_by_the_expiration(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine, datetime.now(UTC) - timedelta(minutes=29, seconds=59))
        cancellation = CancelPaymentIntentUseCase(
            SqlAlchemyCancellationUnitOfWork(engine),
            lambda: datetime.now(UTC),
            InMemoryBusinessEventLogger(),
        )

        cancellation.execute(CancelPaymentCommand("shop", str(intent.id)))

        assert _expire(engine) == 0
        assert _status(engine, intent) == "canceled"


class TestAdditiveMigration0005:
    def test_it_only_adds_an_index_and_keeps_existing_rows_readable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = alembic_config(monkeypatch)
        engine_iter = migrated_engine(monkeypatch, "0004")
        engine = next(engine_iter)
        try:
            intent = add_intent(engine)
            columns_before = self._columns(engine)

            command.upgrade(config, "0005")

            assert self._columns(engine) == columns_before
            assert _status(engine, intent) == "requires_confirmation"
            assert "ix_payment_intents_pending_expiry" in self._indexes(engine)

            command.downgrade(config, "0004")

            assert "ix_payment_intents_pending_expiry" not in self._indexes(engine)
            assert _status(engine, intent) == "requires_confirmation"
        finally:
            engine_iter.close()

    @staticmethod
    def _columns(engine: Engine) -> list[tuple[str, str, str]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'public' ORDER BY table_name, column_name"
                )
            )
            return [(row[0], row[1], row[2]) for row in rows]

    @staticmethod
    def _indexes(engine: Engine) -> set[str]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT indexname FROM pg_indexes"))
            return {row[0] for row in rows}
