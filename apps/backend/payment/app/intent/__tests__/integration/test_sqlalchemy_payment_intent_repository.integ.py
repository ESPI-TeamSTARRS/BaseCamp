from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, StaticPool, create_engine

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_race_error import IdempotencyRaceError
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.base import Base
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


def _pair(order: str = "CMD-1", key: str = "key-0001") -> tuple[PaymentIntent, IdempotencyRecord]:
    intent = PaymentIntent.create(order, Amount(2500), Currency.EUR, NOW, timedelta(minutes=30))
    return intent, IdempotencyRecord("shop", key, "hash", intent.id)


class TestSqlAlchemyPaymentIntentRepository:
    def test_stores_and_reads_back_an_intent_with_integer_amounts(self, engine: Engine) -> None:
        repo = SqlAlchemyPaymentIntentRepository(engine)
        intent, record = _pair()

        repo.add(intent, record)

        found = repo.get_by_id(intent.id)
        assert found is not None
        assert (found.amount.cents, found.refunded_amount) == (2500, 0)
        assert isinstance(found.amount.cents, int)
        assert found.expires_at == intent.expires_at
        assert repo.get_by_order_reference("CMD-1") == found

    def test_unknown_intent_returns_none(self, engine: Engine) -> None:
        repo = SqlAlchemyPaymentIntentRepository(engine)

        assert repo.get_by_id(_pair()[0].id) is None
        assert repo.get_by_order_reference("nope") is None

    def test_finds_an_intent_by_caller_and_idempotency_key(self, engine: Engine) -> None:
        repo = SqlAlchemyPaymentIntentRepository(engine)
        intent, record = _pair()
        repo.add(intent, record)

        found = repo.find_by_idempotency("shop", "key-0001")

        assert found is not None
        assert found[0] == record
        assert found[1].id == intent.id
        assert repo.find_by_idempotency("other", "key-0001") is None

    def test_duplicate_order_reference_is_refused_and_nothing_is_stored(
        self, engine: Engine
    ) -> None:
        repo = SqlAlchemyPaymentIntentRepository(engine)
        repo.add(*_pair())
        other, other_record = _pair(key="key-0002")

        with pytest.raises(DuplicateOrderReferenceError):
            repo.add(other, other_record)

        assert repo.get_by_id(other.id) is None
        assert repo.find_by_idempotency("shop", "key-0002") is None

    def test_concurrent_reuse_of_a_key_is_reported_as_a_race(self, engine: Engine) -> None:
        repo = SqlAlchemyPaymentIntentRepository(engine)
        repo.add(*_pair())
        other, _ = _pair(order="CMD-2")

        with pytest.raises(IdempotencyRaceError):
            repo.add(other, IdempotencyRecord("shop", "key-0001", "hash", other.id))
