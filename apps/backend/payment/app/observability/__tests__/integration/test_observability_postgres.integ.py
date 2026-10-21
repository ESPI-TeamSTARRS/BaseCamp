"""Lecture d'état et /metrics sur un vrai Postgres (SQL propre à Postgres : SUM en NUMERIC, EXISTS).

Exécuté si PAYMENT_TEST_DATABASE_URL désigne une base Postgres JETABLE (schéma créé par
`alembic upgrade head`, puis supprimé).
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import Settings
from app.main import create_app
from app.observability.__tests__.integration.seeding import add_entries, add_intent, add_outbox
from app.observability.infrastructure.repositories.sqlalchemy_service_state_reader import (
    SqlAlchemyServiceStateReader,
)

DATABASE_URL = os.environ.get("PAYMENT_TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[4]
NOW = datetime.now(UTC)
RECENT = NOW - timedelta(minutes=5)

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="définir PAYMENT_TEST_DATABASE_URL (Postgres jetable)"
)


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
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
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")


class TestStateOnPostgres:
    def test_an_empty_schema_reports_zeros(self, engine: Engine) -> None:
        state = SqlAlchemyServiceStateReader(engine, timedelta(hours=24)).read(NOW)

        assert state is not None
        assert state.captured_amount_cents == 0
        assert set(state.ledger_discrepancies.values()) == {0}

    def test_payments_events_and_discrepancies_are_read(self, engine: Engine) -> None:
        paid = add_intent(engine, RECENT, "succeeded", amount=5000, refunded=1000)
        add_entries(engine, paid, RECENT, debit=5000, credit=5000)
        add_intent(engine, RECENT, "succeeded", amount=3000)  # écart : aucune écriture
        add_outbox(engine, paid, "pending", NOW - timedelta(seconds=40))
        add_outbox(engine, paid, "dead", RECENT, "payment.failed")

        state = SqlAlchemyServiceStateReader(engine, timedelta(hours=24)).read(NOW)

        assert state is not None
        assert state.intents_by_status["succeeded"] == 2
        assert (state.captured_amount_cents, state.refunded_amount_cents) == (8000, 1000)
        assert state.refunded_intents == 1
        assert state.webhook_events_by_status["pending"] == 1
        assert state.webhook_events_by_status["dead"] == 1
        assert 39 <= state.webhook_oldest_pending_age_seconds <= 120
        assert state.ledger_discrepancies["succeeded_without_entries"] == 1
        assert state.ledger_discrepancies["amount_mismatch"] == 0
        assert state.ledger_discrepancies["unbalanced_transaction"] == 0

    def test_the_endpoint_serves_the_postgres_state(self, engine: Engine) -> None:
        add_intent(engine, RECENT, "succeeded", amount=5000)
        application = create_app(Settings(), engine)

        with TestClient(application) as client:
            text = client.get("/metrics").text

        assert 'payment_intents{status="succeeded"} 1' in text
        assert "payment_state_up 1" in text
