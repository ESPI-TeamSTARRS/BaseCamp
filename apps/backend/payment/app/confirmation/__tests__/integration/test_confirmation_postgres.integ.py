"""Garanties qui n'existent que sur Postgres : verrou de ligne, équilibre différé, ajout seul.

Exécutés si PAYMENT_TEST_DATABASE_URL pointe vers une base Postgres JETABLE (le schéma est créé
par `alembic upgrade head` puis supprimé). Sur la pile, les mêmes garanties sont vérifiées par les
scénarios e2e.
"""

import os
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
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
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel

DATABASE_URL = os.environ.get("PAYMENT_TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[4]

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="définir PAYMENT_TEST_DATABASE_URL (Postgres jetable)"
)


class SlowApprovingProvider(PaymentProvider):
    """Élargit la fenêtre de concurrence : la seconde demande arrive pendant la première."""

    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome:
        time.sleep(0.4)
        return ProviderOutcome.APPROVED


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


def _intent(engine: Engine) -> PaymentIntent:
    now = datetime.now(UTC)
    intent = PaymentIntent.create(
        f"CMD-{now.timestamp()}", Amount(2500), Currency.EUR, now, timedelta(minutes=30)
    )
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{intent.id}", "hash", intent.id)
    )
    return intent


def _confirm(engine: Engine, intent: PaymentIntent, key: str) -> None:
    ConfirmPaymentUseCase(
        SqlAlchemyConfirmationUnitOfWork(engine),
        SlowApprovingProvider(),
        lambda: datetime.now(UTC),
    ).execute(ConfirmPaymentCommand("shop", key, str(intent.id), "pm_test_success"))


def _count_entries(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(LedgerEntryModel)) or 0


class TestConcurrency:
    def test_two_concurrent_confirmations_of_the_same_intent_only_one_succeeds(
        self, engine: Engine
    ) -> None:
        intent = _intent(engine)
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def attempt(key: str) -> None:
            barrier.wait()
            try:
                _confirm(engine, intent, key)
                outcomes.append("ok")
            except IntentNotConfirmableError:
                outcomes.append("conflict")

        threads = [threading.Thread(target=attempt, args=(f"key-000{n}",)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(outcomes) == ["conflict", "ok"]
        assert _count_entries(engine) == 2

    def test_two_concurrent_confirmations_with_the_same_key_write_once(
        self, engine: Engine
    ) -> None:
        intent = _intent(engine)
        barrier = threading.Barrier(2)

        def attempt() -> None:
            barrier.wait()
            _confirm(engine, intent, "key-0001")

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert _count_entries(engine) == 2


class TestLedgerGuarantees:
    def _insert(self, engine: Engine, credit: int) -> None:
        intent = _intent(engine)
        with engine.begin() as connection:
            for account, direction, amount in (
                ("client_attente", "debit", 100),
                ("marchand", "credit", credit),
            ):
                connection.execute(
                    text(
                        "INSERT INTO ledger_entries "
                        "(id, transaction_id, intent_id, account, direction, amount, created_at) "
                        "VALUES (gen_random_uuid(), :tx, :intent, :account, :direction, :amount, now())"
                    ),
                    {
                        "tx": "11111111-1111-1111-1111-111111111111",
                        "intent": intent.id,
                        "account": account,
                        "direction": direction,
                        "amount": amount,
                    },
                )

    def test_a_balanced_transaction_is_accepted(self, engine: Engine) -> None:
        self._insert(engine, credit=100)

        assert _count_entries(engine) == 2

    def test_an_unbalanced_transaction_is_refused_at_commit(self, engine: Engine) -> None:
        with pytest.raises(DBAPIError, match="desequilibree"):
            self._insert(engine, credit=90)

        assert _count_entries(engine) == 0

    @pytest.mark.parametrize(
        "statement", ["UPDATE ledger_entries SET amount = 1", "DELETE FROM ledger_entries"]
    )
    def test_lines_cannot_be_updated_or_deleted_even_by_the_owner(
        self, engine: Engine, statement: str
    ) -> None:
        self._insert(engine, credit=100)

        with pytest.raises(DBAPIError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text(statement))

        assert _count_entries(engine) == 2

    def test_the_table_cannot_be_truncated(self, engine: Engine) -> None:
        self._insert(engine, credit=100)

        with pytest.raises(DBAPIError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text("TRUNCATE ledger_entries"))
