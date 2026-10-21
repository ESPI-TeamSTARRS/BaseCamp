from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, StaticPool, create_engine, event, select
from sqlalchemy.orm import Session

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.base import Base
from app.intent.infrastructure.repositories.sqlalchemy_payment_intent_repository import (
    SqlAlchemyPaymentIntentRepository,
)
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.value_objects.retry_policy import RetryPolicy
from app.webhook.infrastructure.mappers.outbox_event_mapper import OutboxEventMapper
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel
from app.webhook.infrastructure.repositories.sqlalchemy_delivery_unit_of_work import (
    SqlAlchemyDeliveryUnitOfWork,
)
from app.webhook.infrastructure.repositories.sqlalchemy_outbox_repository import (
    SqlAlchemyOutboxRepository,
)

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
POLICY = RetryPolicy(max_attempts=2, base_seconds=5, max_delay_seconds=60)


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


def _intent(engine: Engine, order: str) -> PaymentIntent:
    intent = PaymentIntent.create(order, Amount(2500), Currency.EUR, NOW, timedelta(minutes=30))
    SqlAlchemyPaymentIntentRepository(engine).add(
        intent, IdempotencyRecord("shop", f"create-{order}", "hash", intent.id)
    )
    return intent


def _add(engine: Engine, order: str, at: datetime = NOW) -> OutboxEvent:
    intent = _intent(engine, order)
    outbox_event = OutboxEvent.pending(
        uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, intent.id, f'{{"order":"{order}"}}', at
    )
    with Session(engine) as session:
        SqlAlchemyOutboxRepository(session).add(outbox_event)
        session.commit()
    return outbox_event


def _stored(engine: Engine, event_id: object) -> OutboxEvent:
    with Session(engine) as session:
        model = session.scalars(
            select(OutboxEventModel).where(OutboxEventModel.id == event_id)
        ).one()
        return OutboxEventMapper.to_entity(model)


class TestClaim:
    def test_nothing_is_claimed_when_the_outbox_is_empty(self, engine: Engine) -> None:
        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            assert session.claim_next_due(NOW) is None

    def test_the_oldest_due_pending_event_is_claimed_first(self, engine: Engine) -> None:
        newer = _add(engine, "CMD-2", NOW)
        older = _add(engine, "CMD-1", NOW - timedelta(minutes=5))

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            first = session.claim_next_due(NOW)

        assert first == older
        assert newer.id != older.id

    def test_an_event_scheduled_in_the_future_is_not_claimed(self, engine: Engine) -> None:
        _add(engine, "CMD-1", NOW + timedelta(seconds=1))

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            assert session.claim_next_due(NOW) is None

    def test_delivered_and_dead_events_are_never_claimed(self, engine: Engine) -> None:
        delivered = _add(engine, "CMD-1")
        dead = _add(engine, "CMD-2")
        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            session.save(delivered.mark_delivered(NOW))
            session.save(dead.mark_failed(NOW, "http_500", POLICY).mark_failed(NOW, "x", POLICY))

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            assert session.claim_next_due(NOW + timedelta(days=1)) is None


class TestSave:
    def test_the_attempt_counter_the_schedule_and_the_error_are_persisted(
        self, engine: Engine
    ) -> None:
        added = _add(engine, "CMD-1")
        failed = added.mark_failed(NOW, "http_503", POLICY)

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            session.save(failed)

        stored = _stored(engine, added.id)
        assert stored == failed
        assert (stored.attempts, stored.last_error) == (1, "http_503")
        assert stored.next_attempt_at == NOW + timedelta(seconds=5)

    def test_an_error_inside_the_block_rolls_the_change_back(self, engine: Engine) -> None:
        added = _add(engine, "CMD-1")

        with pytest.raises(RuntimeError), SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            session.save(added.mark_delivered(NOW))
            raise RuntimeError

        assert _stored(engine, added.id).status is OutboxStatus.PENDING


class TestFindDead:
    def test_one_dead_event_or_all_of_them(self, engine: Engine) -> None:
        first, second, alive = _add(engine, "CMD-1"), _add(engine, "CMD-2"), _add(engine, "CMD-3")
        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            for event_ in (first, second):
                session.save(
                    event_.mark_failed(NOW, "timeout", POLICY).mark_failed(NOW, "timeout", POLICY)
                )

        with SqlAlchemyDeliveryUnitOfWork(engine).begin() as session:
            everyone = {e.id for e in session.find_dead(None)}
            only_first = [e.id for e in session.find_dead(first.id)]
            not_dead = session.find_dead(alive.id)

        assert everyone == {first.id, second.id}
        assert only_first == [first.id]
        assert not_dead == []
