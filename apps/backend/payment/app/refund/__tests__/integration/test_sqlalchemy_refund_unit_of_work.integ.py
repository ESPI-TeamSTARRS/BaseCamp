from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, StaticPool, create_engine, event, func, select, text
from sqlalchemy.orm import Session

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.base import Base
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from app.refund.domain.entities.refund import Refund
from app.refund.domain.exceptions.refund_key_reused_error import RefundKeyReusedError
from app.refund.infrastructure.models.refund_model import RefundModel
from app.refund.infrastructure.repositories.sqlalchemy_refund_unit_of_work import (
    SqlAlchemyRefundUnitOfWork,
)
from app.webhook.domain.services.refund_event_factory import RefundEventFactory
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


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


def _paid_intent(engine: Engine, order: str = "CMD-1") -> PaymentIntent:
    intent = PaymentIntent.create(order, Amount(10000), Currency.EUR, NOW, timedelta(minutes=30))
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{order}", "hash", intent.id)
    )
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE payment_intents SET status = 'succeeded' WHERE order_reference = :o"),
            {"o": order},
        )
    return intent.succeed()


def _count(engine: Engine, model: type) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _refund_of(
    intent: PaymentIntent, key: str, cents: int = 4000
) -> tuple[PaymentIntent, Refund, LedgerTransaction]:
    amount = Amount(cents)
    refunded = intent.refund(amount)
    refund = Refund.issue(intent.id, amount, refunded.refunded_amount, "shop", key, "hash", NOW)
    return refunded, refund, LedgerTransaction.refund_issued(intent.id, amount, NOW)


class TestSession:
    def test_lock_intent_returns_the_stored_intent_or_nothing(self, engine: Engine) -> None:
        intent = _paid_intent(engine)

        with SqlAlchemyRefundUnitOfWork(engine).begin() as session:
            found = session.lock_intent(intent.id)
            missing = session.lock_intent(uuid4())

        assert found == intent
        assert missing is None

    def test_find_refund_is_scoped_by_caller_and_key(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        refunded, refund, ledger = _refund_of(intent, "refund-0001")
        unit_of_work = SqlAlchemyRefundUnitOfWork(engine)
        with unit_of_work.begin() as session:
            session.save(
                refunded,
                refund,
                ledger,
                RefundEventFactory().build(refunded, refund.id, refund.amount, NOW),
            )

        with unit_of_work.begin() as session:
            assert session.find_refund("shop", "refund-0001") == refund
            assert session.find_refund("other", "refund-0001") is None
            assert session.find_refund("shop", "refund-0002") is None


class TestSave:
    def test_the_refund_the_cumulated_amount_the_ledger_and_the_event_are_written_together(
        self, engine: Engine
    ) -> None:
        intent = _paid_intent(engine)
        refunded, refund, ledger = _refund_of(intent, "refund-0001")

        with SqlAlchemyRefundUnitOfWork(engine).begin() as session:
            session.save(
                refunded,
                refund,
                ledger,
                RefundEventFactory().build(refunded, refund.id, refund.amount, NOW),
            )

        stored = SqlAlchemyPaymentIntentRepository(engine).get_by_id(intent.id)
        assert stored is not None
        assert stored.refunded_amount == 4000
        assert _count(engine, RefundModel) == 1
        assert _count(engine, LedgerEntryModel) == 2
        assert _count(engine, OutboxEventModel) == 1

    def test_a_key_already_used_for_another_intent_aborts_everything(self, engine: Engine) -> None:
        first, second = _paid_intent(engine, "CMD-1"), _paid_intent(engine, "CMD-2")
        unit_of_work = SqlAlchemyRefundUnitOfWork(engine)
        refunded, refund, ledger = _refund_of(first, "refund-0001")
        with unit_of_work.begin() as session:
            session.save(
                refunded,
                refund,
                ledger,
                RefundEventFactory().build(refunded, refund.id, refund.amount, NOW),
            )
        other_refunded, other, other_ledger = _refund_of(second, "refund-0001")

        with pytest.raises(RefundKeyReusedError), unit_of_work.begin() as session:
            session.save(
                other_refunded,
                other,
                other_ledger,
                RefundEventFactory().build(other_refunded, other.id, other.amount, NOW),
            )

        untouched = SqlAlchemyPaymentIntentRepository(engine).get_by_id(second.id)
        assert untouched is not None
        assert untouched.refunded_amount == 0
        assert _count(engine, RefundModel) == 1
        assert _count(engine, LedgerEntryModel) == 2
        assert _count(engine, OutboxEventModel) == 1

    def test_an_error_inside_the_block_rolls_everything_back(self, engine: Engine) -> None:
        intent = _paid_intent(engine)
        refunded, refund, ledger = _refund_of(intent, "refund-0001")

        with pytest.raises(RuntimeError), SqlAlchemyRefundUnitOfWork(engine).begin() as session:
            session.save(
                refunded,
                refund,
                ledger,
                RefundEventFactory().build(refunded, refund.id, refund.amount, NOW),
            )
            raise RuntimeError

        assert _count(engine, RefundModel) == 0
        assert _count(engine, LedgerEntryModel) == 0
        assert _count(engine, OutboxEventModel) == 0
