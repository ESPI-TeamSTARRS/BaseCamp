"""Points d'entrée d'exploitation : worker de livraison et commande de relance."""

import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.webhook.__tests__.support import InMemoryDeliveryUnitOfWork, InMemoryOutbox
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.value_objects.retry_policy import RetryPolicy
from app.webhook.presentation import requeue_main, worker_main

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
POLICY = RetryPolicy(max_attempts=1, base_seconds=1, max_delay_seconds=2)


def _dead(outbox: InMemoryOutbox) -> OutboxEvent:
    event = OutboxEvent.pending(uuid4(), WebhookEventType.PAYMENT_FAILED, uuid4(), "{}", NOW)
    dead = event.mark_failed(NOW, "http_500", POLICY)
    outbox.events[dead.id] = dead
    return dead


def _use_case(outbox: InMemoryOutbox) -> RequeueDeadEventsUseCase:
    return RequeueDeadEventsUseCase(
        InMemoryDeliveryUnitOfWork(outbox), lambda: NOW, InMemoryBusinessEventLogger()
    )


class TestRequeueCommand:
    def test_one_event_id_requeues_that_event(self) -> None:
        outbox, out = InMemoryOutbox(), io.StringIO()
        dead = _dead(outbox)

        code = requeue_main.run(["--event-id", str(dead.id)], _use_case(outbox), out)

        assert code == 0
        assert "1" in out.getvalue()
        assert outbox.events[dead.id].attempts == 0

    def test_all_requeues_every_dead_event(self) -> None:
        outbox, out = InMemoryOutbox(), io.StringIO()
        _dead(outbox)
        _dead(outbox)

        code = requeue_main.run(["--all"], _use_case(outbox), out)

        assert code == 0
        assert "2" in out.getvalue()

    def test_an_unknown_or_not_dead_event_is_an_error_exit(self) -> None:
        out = io.StringIO()

        code = requeue_main.run(["--event-id", str(uuid4())], _use_case(InMemoryOutbox()), out)

        assert code == 1
        assert "aucun" in out.getvalue().lower()

    def test_an_invalid_identifier_is_refused_before_touching_the_database(self) -> None:
        with pytest.raises(SystemExit) as stop:
            requeue_main.run(
                ["--event-id", "not-a-uuid"], _use_case(InMemoryOutbox()), io.StringIO()
            )

        assert stop.value.code == 2

    def test_one_of_event_id_or_all_is_required(self) -> None:
        with pytest.raises(SystemExit) as stop:
            requeue_main.run([], _use_case(InMemoryOutbox()), io.StringIO())

        assert stop.value.code == 2


class TestWorkerStartup:
    @pytest.mark.parametrize(
        "environment",
        [
            {},
            {"APP_WEBHOOK_URL": "http://shop:8000/hook"},
            {"APP_WEBHOOK_SECRET": "x" * 40},
        ],
    )
    def test_the_worker_refuses_to_start_without_url_and_secret(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        environment: dict[str, str],
    ) -> None:
        for name, value in environment.items():
            monkeypatch.setenv(name, value)

        code = worker_main.main()

        assert code == 2
        captured = capsys.readouterr()
        assert "APP_WEBHOOK_URL" in captured.err
        assert "x" * 40 not in captured.err + captured.out
