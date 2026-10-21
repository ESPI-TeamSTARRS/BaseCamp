from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.value_objects.retry_policy import RetryPolicy

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
POLICY = RetryPolicy(max_attempts=3, base_seconds=5, max_delay_seconds=60)


def _event() -> OutboxEvent:
    return OutboxEvent.pending(uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, uuid4(), "{}", NOW)


class TestPending:
    def test_a_new_event_is_pending_and_due_immediately(self) -> None:
        event = _event()

        assert event.status is OutboxStatus.PENDING
        assert (event.attempts, event.next_attempt_at, event.created_at) == (0, NOW, NOW)
        assert event.last_error is None
        assert event.delivered_at is None


class TestDelivered:
    def test_a_delivery_counts_the_attempt_and_closes_the_event(self) -> None:
        later = NOW + timedelta(seconds=3)

        event = _event().mark_delivered(later)

        assert event.status is OutboxStatus.DELIVERED
        assert (event.attempts, event.delivered_at, event.last_error) == (1, later, None)


class TestFailed:
    def test_a_failure_schedules_the_next_attempt_with_exponential_waiting(self) -> None:
        first = _event().mark_failed(NOW, "http_500", POLICY)
        second = first.mark_failed(NOW, "timeout", POLICY)

        assert first.status is second.status is OutboxStatus.PENDING
        assert first.next_attempt_at == NOW + timedelta(seconds=5)
        assert second.next_attempt_at == NOW + timedelta(seconds=10)
        assert (first.attempts, second.attempts, second.last_error) == (1, 2, "timeout")

    def test_the_event_id_never_changes_between_attempts(self) -> None:
        event = _event()

        assert event.mark_failed(NOW, "http_500", POLICY).id == event.id

    def test_the_last_allowed_failure_makes_the_event_dead(self) -> None:
        event = _event()
        for _ in range(3):
            event = event.mark_failed(NOW, "connection_error", POLICY)

        assert event.status is OutboxStatus.DEAD
        assert (event.attempts, event.last_error) == (3, "connection_error")

    def test_the_error_is_a_code_never_free_text(self) -> None:
        with pytest.raises(ValueError, match="code"):
            _event().mark_failed(NOW, "HTTPError: secret in the message", POLICY)


class TestRequeue:
    def test_a_dead_event_goes_back_to_pending_with_a_fresh_budget(self) -> None:
        dead = _event()
        for _ in range(3):
            dead = dead.mark_failed(NOW, "http_503", POLICY)

        again = dead.requeue(NOW + timedelta(hours=1))

        assert again.status is OutboxStatus.PENDING
        assert (again.attempts, again.next_attempt_at) == (0, NOW + timedelta(hours=1))
        assert again.id == dead.id
        assert again.body == dead.body

    @pytest.mark.parametrize("step", ["pending", "delivered"])
    def test_only_a_dead_event_can_be_requeued(self, step: str) -> None:
        event = _event() if step == "pending" else _event().mark_delivered(NOW)

        with pytest.raises(ValueError, match="dead"):
            event.requeue(NOW)
