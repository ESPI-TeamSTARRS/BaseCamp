from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.expiration.application import expiration_event_names as names
from app.expiration.application.expire_unconfirmed_intents import ExpireUnconfirmedIntentsUseCase
from app.expiration.domain.interfaces.intent_expiry_repository import IntentExpiryRepository
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount

CREATED = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
TTL = timedelta(minutes=30)
DEADLINE = CREATED + TTL


class InMemoryExpiryRepository(IntentExpiryRepository):
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.calls: list[tuple[datetime, int]] = []

    def expire_overdue(self, now: datetime, limit: int) -> list[PaymentIntent]:
        self.calls.append((now, limit))
        due = [
            i
            for i in sorted(self.intents.values(), key=lambda i: i.expires_at)
            if i.status is IntentStatus.REQUIRES_CONFIRMATION and i.is_overdue(now)
        ][:limit]
        expired = [intent.expire() for intent in due]
        self.intents.update({intent.id: intent for intent in expired})
        return expired


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Fixture:
    def __init__(self, batch_size: int = 100) -> None:
        self.repository = InMemoryExpiryRepository()
        self.logger = InMemoryBusinessEventLogger()
        self.clock = Clock(DEADLINE)
        self.use_case = ExpireUnconfirmedIntentsUseCase(
            self.repository, self.clock, batch_size, self.logger
        )

    def add(self, order: str, status: IntentStatus = IntentStatus.REQUIRES_CONFIRMATION) -> UUID:
        intent = PaymentIntent.create(order, Amount(4990), Currency.EUR, CREATED, TTL)
        self.repository.intents[intent.id] = replace(intent, status=status)
        return intent.id

    def status(self, intent_id: UUID) -> IntentStatus:
        return self.repository.intents[intent_id].status

    def summary(self) -> list[tuple[str, Outcome, str | None]]:
        return [(e.event, e.outcome, e.reason) for e in self.logger.events]


class TestExpiration:
    def test_an_unconfirmed_intent_past_its_deadline_becomes_expired(self) -> None:
        fx = Fixture()
        overdue = fx.add("CMD-1")

        result = fx.use_case.execute()

        assert fx.status(overdue) is IntentStatus.EXPIRED
        assert result.expired_count == 1

    def test_an_intent_still_within_its_deadline_is_left_alone(self) -> None:
        fx = Fixture()
        pending = fx.add("CMD-1")
        fx.clock.now = DEADLINE - timedelta(seconds=1)

        result = fx.use_case.execute()

        assert fx.status(pending) is IntentStatus.REQUIRES_CONFIRMATION
        assert result.expired_count == 0

    @pytest.mark.parametrize(
        "status", [IntentStatus.SUCCEEDED, IntentStatus.FAILED, IntentStatus.CANCELED]
    )
    def test_an_intent_already_settled_or_canceled_is_never_expired(
        self, status: IntentStatus
    ) -> None:
        fx = Fixture()
        settled = fx.add("CMD-1", status)

        fx.use_case.execute()

        assert fx.status(settled) is status

    def test_the_deadline_is_read_from_the_injected_clock(self) -> None:
        fx = Fixture()
        intent = fx.add("CMD-1")
        fx.clock.now = DEADLINE - timedelta(minutes=1)
        fx.use_case.execute()
        assert fx.status(intent) is IntentStatus.REQUIRES_CONFIRMATION

        fx.clock.now = DEADLINE + timedelta(minutes=1)
        fx.use_case.execute()

        assert fx.status(intent) is IntentStatus.EXPIRED

    def test_running_twice_has_no_second_effect(self) -> None:
        fx = Fixture()
        fx.add("CMD-1")
        first = fx.use_case.execute()
        fx.logger.events.clear()

        second = fx.use_case.execute()

        assert (first.expired_count, second.expired_count) == (1, 0)
        assert fx.logger.events == []

    def test_a_backlog_larger_than_a_batch_is_processed_batch_by_batch(self) -> None:
        fx = Fixture(batch_size=2)
        ids = [fx.add(f"CMD-{n}") for n in range(5)]

        result = fx.use_case.execute()

        assert result.expired_count == 5
        assert all(fx.status(i) is IntentStatus.EXPIRED for i in ids)
        assert [limit for _, limit in fx.repository.calls] == [2, 2, 2]

    def test_a_backlog_that_is_an_exact_multiple_of_the_batch_ends_with_an_empty_batch(
        self,
    ) -> None:
        fx = Fixture(batch_size=2)
        for n in range(4):
            fx.add(f"CMD-{n}")

        result = fx.use_case.execute()

        assert result.expired_count == 4
        assert len(fx.repository.calls) == 3


class TestBusinessEvents:
    def test_each_expired_intent_is_logged_then_the_run_is_summarised(self) -> None:
        fx = Fixture()
        first, second = fx.add("CMD-1"), fx.add("CMD-2")

        fx.use_case.execute()

        assert fx.summary() == [
            (names.PAYMENT_EXPIRED, Outcome.SUCCESS, None),
            (names.PAYMENT_EXPIRED, Outcome.SUCCESS, None),
            (names.PAYMENT_EXPIRATION_COMPLETED, Outcome.SUCCESS, None),
        ]
        ids = {e.resource_id for e in fx.logger.events[:2]}
        assert ids == {str(first), str(second)}
        expired, _, completed = fx.logger.events
        assert expired.resource_type == "payment_intent"
        assert expired.actor_id is None
        assert expired.attributes["amount_cents"] == 4990
        assert expired.attributes["currency"] == "EUR"
        assert completed.attributes == {"expired_count": 2}

    def test_nothing_is_logged_when_nothing_expires(self) -> None:
        fx = Fixture()

        fx.use_case.execute()

        assert fx.logger.events == []

    def test_no_ledger_or_secret_detail_is_part_of_the_events(self) -> None:
        fx = Fixture()
        fx.add("CMD-1")

        fx.use_case.execute()

        assert "ledger" not in repr(fx.logger.events)
