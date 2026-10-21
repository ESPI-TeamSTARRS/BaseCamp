from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from sqlalchemy import Engine, StaticPool, create_engine, event, func, select, text
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.orm import Session

from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.base import Base
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    return engine


def _intent(engine: Engine, order: str = "CMD-1") -> PaymentIntent:
    intent = PaymentIntent.create(order, Amount(2500), Currency.EUR, NOW, timedelta(minutes=30))
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{order}", "hash", intent.id)
    )
    return intent


def _ledger_rows(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(LedgerEntryModel)) or 0


def _status(engine: Engine, intent: PaymentIntent) -> IntentStatus:
    found = SqlAlchemyPaymentIntentRepository(engine).get_by_id(intent.id)
    assert found is not None
    return found.status


class TestUnitOfWork:
    def test_locks_and_reads_an_intent_and_returns_none_for_an_unknown_one(
        self, engine: Engine
    ) -> None:
        intent = _intent(engine)

        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            assert session.lock_intent(intent.id) == intent
            assert session.lock_intent(uuid4()) is None

    def test_saves_the_status_the_key_and_both_ledger_entries_together(
        self, engine: Engine
    ) -> None:
        intent = _intent(engine)
        ledger = LedgerTransaction.payment_received(intent.id, intent.amount, NOW)
        record = ConfirmationRecord("shop", "key-0001", "hash", intent.id)

        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            session.save(intent.succeed(), record, ledger)

        assert _status(engine, intent) is IntentStatus.SUCCEEDED
        assert _ledger_rows(engine) == 2
        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            assert session.find_record("shop", "key-0001") == record
            assert session.find_record("other", "key-0001") is None

    def test_a_failed_confirmation_stores_the_key_without_ledger_entries(
        self, engine: Engine
    ) -> None:
        intent = _intent(engine)

        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            session.save(
                intent.fail(), ConfirmationRecord("shop", "key-0001", "hash", intent.id), None
            )

        assert _status(engine, intent) is IntentStatus.FAILED
        assert _ledger_rows(engine) == 0

    def test_an_error_inside_the_block_rolls_everything_back(self, engine: Engine) -> None:
        intent = _intent(engine)
        ledger = LedgerTransaction.payment_received(intent.id, intent.amount, NOW)

        with pytest.raises(RuntimeError), SqlAlchemyConfirmationUnitOfWork(engine).begin() as s:
            s.save(intent.succeed(), ConfirmationRecord("shop", "k-00001", "h", intent.id), ledger)
            raise RuntimeError

        assert _status(engine, intent) is IntentStatus.REQUIRES_CONFIRMATION
        assert _ledger_rows(engine) == 0

    def test_a_ledger_write_failure_leaves_the_intent_untouched(self, engine: Engine) -> None:
        intent = _intent(engine)
        ledger = LedgerTransaction.payment_received(intent.id, intent.amount, NOW)
        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            session.save(
                intent.succeed(), ConfirmationRecord("shop", "key-0001", "hash", intent.id), ledger
            )
        other = _intent(engine, "CMD-2")

        with (
            pytest.raises(IntegrityError),
            SqlAlchemyConfirmationUnitOfWork(engine).begin() as session,
        ):
            # mêmes identifiants de lignes : l'écriture du grand livre échoue
            session.save(
                other.succeed(), ConfirmationRecord("shop", "key-0002", "hash", other.id), ledger
            )

        assert _status(engine, other) is IntentStatus.REQUIRES_CONFIRMATION

    def test_a_key_already_taken_by_another_confirmation_is_reported(self, engine: Engine) -> None:
        first, second = _intent(engine), _intent(engine, "CMD-2")
        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            session.save(first.fail(), ConfirmationRecord("shop", "key-0001", "a", first.id), None)

        with (
            pytest.raises(ConfirmationKeyReusedError),
            SqlAlchemyConfirmationUnitOfWork(engine).begin() as session,
        ):
            session.save(
                second.fail(), ConfirmationRecord("shop", "key-0001", "b", second.id), None
            )

        assert _status(engine, second) is IntentStatus.REQUIRES_CONFIRMATION


class TestLedgerIsAppendOnly:
    def _write_one_transaction(self, engine: Engine) -> None:
        intent = _intent(engine)
        ledger = LedgerTransaction.payment_received(intent.id, intent.amount, NOW)
        with SqlAlchemyConfirmationUnitOfWork(engine).begin() as session:
            session.save(
                intent.succeed(), ConfirmationRecord("shop", "key-0001", "hash", intent.id), ledger
            )

    def test_a_ledger_line_cannot_be_updated(self, engine: Engine) -> None:
        self._write_one_transaction(engine)

        with pytest.raises(DatabaseError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text("UPDATE ledger_entries SET amount = 1"))

    def test_a_ledger_line_cannot_be_deleted(self, engine: Engine) -> None:
        self._write_one_transaction(engine)

        with pytest.raises(DatabaseError, match="ajout seul"), engine.begin() as connection:
            connection.execute(text("DELETE FROM ledger_entries"))

        assert _ledger_rows(engine) == 2
