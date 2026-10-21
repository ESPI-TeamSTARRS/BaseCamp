"""Garanties du remboursement qui n'existent que sur Postgres : verrou, plafond en base, migration.

Exécutés si PAYMENT_TEST_DATABASE_URL pointe vers une base Postgres JETABLE (le schéma est créé
par `alembic upgrade head` puis supprimé). Sur la pile, les mêmes garanties sont vérifiées par
les scénarios e2e.
"""

import os
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.application.dtos.refund_view import RefundView
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.refund.domain.exceptions.refund_exceeds_captured_error import RefundExceedsCapturedError
from app.refund.infrastructure.models.refund_model import RefundModel
from app.refund.infrastructure.repositories.sqlalchemy_refund_unit_of_work import (
    SqlAlchemyRefundUnitOfWork,
)
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel

DATABASE_URL = os.environ.get("PAYMENT_TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[4]
CAPTURED = 10000

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="définir PAYMENT_TEST_DATABASE_URL (Postgres jetable)"
)


def _config(monkeypatch: pytest.MonkeyPatch) -> Config:
    assert DATABASE_URL
    url = make_url(DATABASE_URL)
    for name, value in {
        "APP_DB_HOST": url.host,
        "APP_DB_PORT": url.port,
        "APP_DB_NAME": url.database,
        "APP_DB_USER": url.username,
        "APP_DB_PASSWORD": url.password,
    }.items():
        monkeypatch.setenv(name, str(value))
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return config


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert DATABASE_URL
    config = _config(monkeypatch)
    command.upgrade(config, "head")
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")


def _paid_intent(engine: Engine) -> PaymentIntent:
    now = datetime.now(UTC)
    intent = PaymentIntent.create(
        f"CMD-{now.timestamp()}", Amount(CAPTURED), Currency.EUR, now, timedelta(minutes=30)
    )
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{intent.id}", "hash", intent.id)
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE payment_intents SET status = 'succeeded' WHERE id = :id"),
            {"id": intent.id},
        )
    return intent.succeed()


def _use_case(engine: Engine, pause: float = 0.0) -> RefundPaymentUseCase:
    """`pause` est dormi pendant que l'intention est verrouillée : il élargit la fenêtre de course."""

    def clock() -> datetime:
        time.sleep(pause)
        return datetime.now(UTC)

    return RefundPaymentUseCase(
        SqlAlchemyRefundUnitOfWork(engine), clock, InMemoryBusinessEventLogger()
    )


def _command(intent: PaymentIntent, key: str, amount: int) -> RefundPaymentCommand:
    return RefundPaymentCommand("shop", key, str(intent.id), amount)


def _count(engine: Engine, model: type) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _refunded(engine: Engine, intent: PaymentIntent) -> int:
    found = SqlAlchemyPaymentIntentRepository(engine).get_by_id(intent.id)
    assert found is not None
    return found.refunded_amount


def _run_concurrently(
    engine: Engine, intent: PaymentIntent, attempts: list[tuple[str, int]]
) -> list[str]:
    barrier = threading.Barrier(len(attempts))
    outcomes: list[str] = []
    use_case = _use_case(engine, pause=0.3)

    def attempt(key: str, amount: int) -> None:
        barrier.wait()
        try:
            use_case.execute(_command(intent, key, amount))
            outcomes.append("ok")
        except RefundExceedsCapturedError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=attempt, args=item) for item in attempts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


class TestConcurrency:
    def test_two_concurrent_refunds_that_would_exceed_the_total_only_one_succeeds(
        self, engine: Engine
    ) -> None:
        intent = _paid_intent(engine)
        _use_case(engine).execute(_command(intent, "refund-0000", 4000))

        outcomes = _run_concurrently(engine, intent, [("refund-0001", 6000), ("refund-0002", 6000)])

        assert outcomes == ["conflict", "ok"]
        assert _refunded(engine, intent) == CAPTURED
        assert _count(engine, RefundModel) == 2
        assert _count(engine, LedgerEntryModel) == 4
        assert _count(engine, OutboxEventModel) == 2

    def test_many_concurrent_refunds_never_exceed_the_captured_amount(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        attempts = [(f"refund-{n:04d}", 3000) for n in range(8)]

        outcomes = _run_concurrently(engine, intent, attempts)

        assert outcomes == ["conflict"] * 5 + ["ok"] * 3
        assert _refunded(engine, intent) == 9000
        with Session(engine) as session:
            assert session.scalar(select(func.sum(RefundModel.amount))) == 9000

    def test_two_concurrent_refunds_with_the_same_key_write_once(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        barrier = threading.Barrier(2)
        views: list[RefundView] = []
        use_case = _use_case(engine, pause=0.3)

        def attempt() -> None:
            barrier.wait()
            views.append(use_case.execute(_command(intent, "refund-0001", 4000)))

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert views[0] == views[1]
        assert _refunded(engine, intent) == 4000
        assert _count(engine, RefundModel) == 1
        assert _count(engine, LedgerEntryModel) == 2
        assert _count(engine, OutboxEventModel) == 1


class TestCeilingIsEnforcedByTheDatabase:
    """Même sans le code applicatif (accès direct, bug, autre client), la base refuse l'excès."""

    def _insert_refund(self, engine: Engine, intent: PaymentIntent, key: str, amount: int) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO refunds (id, intent_id, amount, amount_refunded, caller, "
                    "idempotency_key, request_hash, created_at) "
                    "VALUES (gen_random_uuid(), :intent, :amount, :amount, 'shop', :key, 'h', now())"
                ),
                {"intent": intent.id, "amount": amount, "key": key},
            )

    def test_a_refund_row_that_would_exceed_the_captured_amount_is_refused(
        self, engine: Engine
    ) -> None:
        intent = _paid_intent(engine)
        self._insert_refund(engine, intent, "direct-0001", 4000)

        with pytest.raises(DBAPIError, match="depassent"):
            self._insert_refund(engine, intent, "direct-0002", 6001)

        assert _count(engine, RefundModel) == 1

    def test_the_exact_remaining_amount_is_accepted(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        self._insert_refund(engine, intent, "direct-0001", 4000)

        self._insert_refund(engine, intent, "direct-0002", 6000)

        assert _count(engine, RefundModel) == 2

    @pytest.mark.parametrize("amount", [0, -5])
    def test_a_non_positive_amount_is_refused(self, engine: Engine, amount: int) -> None:
        intent = _paid_intent(engine)

        with pytest.raises(DBAPIError, match="ck_refunds_amount_positive"):
            self._insert_refund(engine, intent, "direct-0001", amount)

    def test_a_cumulated_amount_above_the_captured_one_is_refused_on_the_intent(
        self, engine: Engine
    ) -> None:
        intent = _paid_intent(engine)

        with (
            pytest.raises(DBAPIError, match="ck_payment_intents_refunded_within_amount"),
            engine.begin() as connection,
        ):
            connection.execute(
                text("UPDATE payment_intents SET refunded_amount = :n WHERE id = :id"),
                {"n": CAPTURED + 1, "id": intent.id},
            )

    def test_the_same_key_cannot_be_inserted_twice_for_a_caller(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        self._insert_refund(engine, intent, "direct-0001", 100)

        with pytest.raises(DBAPIError, match="uq_refunds_caller_key"):
            self._insert_refund(engine, intent, "direct-0001", 100)

    @pytest.mark.parametrize(
        "statement",
        ["UPDATE refunds SET amount = 1", "DELETE FROM refunds", "TRUNCATE refunds"],
    )
    def test_refunds_cannot_be_updated_deleted_or_truncated(
        self, engine: Engine, statement: str
    ) -> None:
        intent = _paid_intent(engine)
        self._insert_refund(engine, intent, "direct-0001", 4000)

        with pytest.raises(DBAPIError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text(statement))

        assert _count(engine, RefundModel) == 1

    def test_the_ledger_stays_balanced_and_append_only_for_refund_lines(
        self, engine: Engine
    ) -> None:
        intent = _paid_intent(engine)
        _use_case(engine).execute(_command(intent, "refund-0001", 4000))

        with pytest.raises(DBAPIError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text("UPDATE ledger_entries SET amount = 1"))
        with engine.connect() as connection:
            totals = connection.execute(
                text(
                    "SELECT account, direction, SUM(amount) FROM ledger_entries "
                    "GROUP BY account, direction ORDER BY account"
                )
            ).all()
        assert [tuple(row) for row in totals] == [
            ("marchand", "debit", 4000),
            ("remboursements", "credit", 4000),
        ]


def _columns(engine: Engine) -> dict[str, list[str]]:
    inspector = inspect(engine)
    return {
        table: sorted(column["name"] for column in inspector.get_columns(table))
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


class TestMigrationIsAdditive:
    def test_the_refund_migration_only_adds_a_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert DATABASE_URL
        config = _config(monkeypatch)
        command.upgrade(config, "0005")
        engine = create_engine(DATABASE_URL)
        try:
            before = _columns(engine)
            command.upgrade(config, "head")
            after = _columns(engine)
        finally:
            engine.dispose()
            command.downgrade(config, "base")

        assert set(after) - set(before) == {"refunds"}
        assert {table: columns for table, columns in after.items() if table != "refunds"} == before

    def test_data_written_before_the_migration_survives_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert DATABASE_URL
        config = _config(monkeypatch)
        command.upgrade(config, "0005")
        engine = create_engine(DATABASE_URL)
        try:
            intent = _paid_intent(engine)
            command.upgrade(config, "head")
            use_case = _use_case(engine)
            view = use_case.execute(_command(intent, "refund-0001", CAPTURED))
        finally:
            engine.dispose()
            command.downgrade(config, "base")

        assert UUID(view.payment_intent_id) == intent.id
        assert view.amount_refunded == CAPTURED
