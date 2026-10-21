"""Aides des tests Postgres (pas un test) : base jetable migrée par Alembic, intentions de test.

Les tests qui s'en servent s'exécutent si PAYMENT_TEST_DATABASE_URL désigne une base Postgres
JETABLE (le schéma est créé par `alembic upgrade`, puis supprimé).
"""

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select
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
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel

DATABASE_URL = os.environ.get("PAYMENT_TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[3]

requires_postgres = pytest.mark.skipif(
    not DATABASE_URL, reason="définir PAYMENT_TEST_DATABASE_URL (Postgres jetable)"
)


def alembic_config(monkeypatch: pytest.MonkeyPatch) -> Config:
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


def migrated_engine(monkeypatch: pytest.MonkeyPatch, revision: str = "head") -> Generator[Engine]:
    """Fournit un moteur sur une base migrée jusqu'à `revision`, vidée à la fin."""
    assert DATABASE_URL
    config = alembic_config(monkeypatch)
    command.upgrade(config, revision)
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")


def add_intent(
    engine: Engine, created: datetime | None = None, ttl: timedelta = timedelta(minutes=30)
) -> PaymentIntent:
    created = created or datetime.now(UTC)
    intent = PaymentIntent.create(
        f"CMD-{created.timestamp()}-{os.urandom(4).hex()}",
        Amount(2500),
        Currency.EUR,
        created,
        ttl,
    )
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{intent.id}", "hash", intent.id)
    )
    return intent


def count_ledger_entries(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(LedgerEntryModel)) or 0
