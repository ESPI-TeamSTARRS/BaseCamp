from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.business_event import BusinessEvent
from app.intent.__tests__.support import LIMIT, InMemoryRepository, make_command
from app.intent.application.create_payment_intent import CreatePaymentIntentUseCase
from app.intent.application.get_payment_intent import GetPaymentIntentUseCase
from app.intent.application.get_payment_intent_by_order import GetPaymentIntentByOrderUseCase
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def _create(repo: InMemoryRepository, events: InMemoryBusinessEventLogger):  # type: ignore[no-untyped-def]
    return CreatePaymentIntentUseCase(repo, lambda: NOW, timedelta(minutes=30), LIMIT, events)


def _summary(event: BusinessEvent) -> tuple[str, str, str | None]:
    return event.event, event.outcome.value, event.reason


class TestCreateEvents:
    def test_a_creation_emits_intent_created_with_amount_and_currency(self) -> None:
        events = InMemoryBusinessEventLogger()

        result = _create(InMemoryRepository(), events).execute(make_command())

        (event,) = events.events
        assert _summary(event) == ("payment.intent_created", "success", None)
        assert (event.resource_type, event.resource_id) == ("payment_intent", str(result.intent.id))
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert event.attributes == {"amount_cents": 2500, "currency": "EUR"}

    def test_an_identical_replay_emits_intent_replayed(self) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = _create(InMemoryRepository(), events)
        use_case.execute(make_command())

        use_case.execute(make_command())

        assert [_summary(e) for e in events.events] == [
            ("payment.intent_created", "success", None),
            ("payment.intent_replayed", "success", None),
        ]

    @pytest.mark.parametrize(
        ("setup", "command", "error", "reason"),
        [
            (False, {"amount": LIMIT + 1}, AmountExceedsLimitError, "amount_exceeds_limit"),
            (True, {"amount": 9999}, IdempotencyKeyReusedError, "idempotency_key_reused"),
            (
                True,
                {"idempotency_key": "key-0002"},
                DuplicateOrderReferenceError,
                "duplicate_order_reference",
            ),
        ],
    )
    def test_a_refusal_emits_intent_rejected_with_a_stable_reason_and_no_key(
        self, setup: bool, command: dict[str, object], error: type[Exception], reason: str
    ) -> None:
        events = InMemoryBusinessEventLogger()
        use_case = _create(InMemoryRepository(), events)
        if setup:
            use_case.execute(make_command())
            events.events.clear()

        with pytest.raises(error):
            use_case.execute(make_command(**command))

        (event,) = events.events
        assert _summary(event) == ("payment.intent_rejected", "denied", reason)
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert "key-000" not in repr(event)


class TestReadEvents:
    def _seed(self, events: InMemoryBusinessEventLogger) -> tuple[InMemoryRepository, str]:
        repo = InMemoryRepository()
        created = _create(repo, InMemoryBusinessEventLogger()).execute(make_command())
        return repo, str(created.intent.id)

    def test_reading_by_id_emits_intent_read(self) -> None:
        events = InMemoryBusinessEventLogger()
        repo, intent_id = self._seed(events)

        GetPaymentIntentUseCase(repo, events).execute(intent_id)

        (event,) = events.events
        assert _summary(event) == ("payment.intent_read", "success", None)
        assert (event.resource_type, event.resource_id) == ("payment_intent", intent_id)
        assert event.attributes == {"lookup": "id"}

    def test_reading_by_order_emits_intent_read(self) -> None:
        events = InMemoryBusinessEventLogger()
        repo, intent_id = self._seed(events)

        GetPaymentIntentByOrderUseCase(repo, events).execute("CMD-1")

        (event,) = events.events
        assert event.resource_id == intent_id
        assert event.attributes == {"lookup": "order"}

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", str(UUID(int=1))])
    def test_an_unknown_id_emits_a_denied_event_without_the_input(self, intent_id: str) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentUseCase(InMemoryRepository(), events).execute(intent_id)

        (event,) = events.events
        assert _summary(event) == ("payment.intent_read", "denied", "not_found")
        assert event.resource_id is None
        assert "not-a-uuid" not in repr(event)

    def test_an_unknown_order_emits_a_denied_event(self) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(PaymentIntentNotFoundError):
            GetPaymentIntentByOrderUseCase(InMemoryRepository(), events).execute("CMD-404")

        assert _summary(events.events[0]) == ("payment.intent_read", "denied", "not_found")
        assert "CMD-404" not in repr(events.events[0])
