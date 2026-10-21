"""Garanties propres à Postgres : migration additive et exclusion des workers (SKIP LOCKED).

Exécutés si PAYMENT_TEST_DATABASE_URL pointe vers une base Postgres JETABLE (le schéma est créé
par `alembic upgrade head`, puis supprimé).
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.infrastructure.repositories.sqlalchemy_delivery_unit_of_work import (
    SqlAlchemyDeliveryUnitOfWork,
)
from app.webhook.infrastructure.repositories.sqlalchemy_outbox_repository import (
    SqlAlchemyOutboxRepository,
)

DATABASE_URL = os.environ.get("PAYMENT_TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[4]

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


def _columns(engine: Engine) -> dict[str, list[str]]:
    inspector = inspect(engine)
    return {
        table: sorted(column["name"] for column in inspector.get_columns(table))
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert DATABASE_URL
    config = _config(monkeypatch)
    command.upgrade(config, "head")
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")


class TestMigrationIsAdditive:
    def test_the_outbox_migration_only_adds_a_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert DATABASE_URL
        config = _config(monkeypatch)
        command.upgrade(config, "0004")
        engine = create_engine(DATABASE_URL)
        try:
            before = _columns(engine)
            command.upgrade(config, "head")
            after = _columns(engine)
        finally:
            engine.dispose()
            command.downgrade(config, "base")

        assert set(after) - set(before) == {"outbox"}
        assert {table: columns for table, columns in after.items() if table != "outbox"} == before

    def test_the_previous_code_can_still_use_the_schema_it_knows(self, engine: Engine) -> None:
        with engine.begin() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }

        assert {
            "payment_intents",
            "idempotency_keys",
            "confirmation_keys",
            "ledger_entries",
        } <= tables


def _event(engine: Engine, order: str) -> OutboxEvent:
    now = datetime.now(UTC)
    intent = PaymentIntent.create(order, Amount(2500), Currency.EUR, now, timedelta(minutes=30))
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{order}", "hash", intent.id)
    )
    outbox_event = OutboxEvent.pending(
        uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, intent.id, "{}", now - timedelta(seconds=5)
    )
    with Session(engine) as session:
        SqlAlchemyOutboxRepository(session).add(outbox_event)
        session.commit()
    return outbox_event


class TestWorkersDoNotOverlap:
    def test_an_event_being_delivered_is_skipped_by_a_second_worker(self, engine: Engine) -> None:
        first, second = _event(engine, "CMD-1"), _event(engine, "CMD-2")
        now = datetime.now(UTC)

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as worker_one:
            claimed_one = worker_one.claim_next_due(now)
            with SqlAlchemyDeliveryUnitOfWork(engine).begin() as worker_two:
                claimed_two = worker_two.claim_next_due(now)
                with SqlAlchemyDeliveryUnitOfWork(engine).begin() as worker_three:
                    nothing_left = worker_three.claim_next_due(now)

        assert claimed_one is not None
        assert claimed_two is not None
        assert {claimed_one.id, claimed_two.id} == {first.id, second.id}
        assert nothing_left is None
