from collections.abc import Callable

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.webhook.application import webhook_event_names as names
from app.webhook.presentation.webhook_worker import WebhookWorker


class FakeDeliver:
    def __init__(self, *outcomes: bool | Exception) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def execute(self) -> bool:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _stop_after(loops: int) -> Callable[[], bool]:
    counter = [0]

    def should_stop() -> bool:
        counter[0] += 1
        return counter[0] > loops

    return should_stop


class TestWebhookWorker:
    def test_it_keeps_delivering_without_waiting_while_events_are_due(self) -> None:
        waits: list[float] = []
        deliver = FakeDeliver(True, True, True)
        should_stop = _stop_after(3)

        WebhookWorker(deliver.execute, InMemoryBusinessEventLogger(), 1.5, waits.append).run(
            should_stop
        )

        assert deliver.calls == 3
        assert waits == []

    def test_it_sleeps_for_the_poll_interval_when_nothing_is_due(self) -> None:
        waits: list[float] = []
        deliver = FakeDeliver(False, True, False)
        should_stop = _stop_after(3)

        WebhookWorker(deliver.execute, InMemoryBusinessEventLogger(), 1.5, waits.append).run(
            should_stop
        )

        assert waits == [1.5, 1.5]

    def test_it_stops_cleanly_when_asked_to(self) -> None:
        deliver = FakeDeliver()

        WebhookWorker(deliver.execute, InMemoryBusinessEventLogger(), 1.0, lambda _: None).run(
            lambda: True
        )

        assert deliver.calls == 0

    def test_an_unexpected_error_is_logged_without_its_message_and_the_loop_survives(self) -> None:
        logger = InMemoryBusinessEventLogger()
        waits: list[float] = []
        deliver = FakeDeliver(RuntimeError("password=hunter2 in the message"), True)
        should_stop = _stop_after(2)

        WebhookWorker(deliver.execute, logger, 2.0, waits.append).run(should_stop)

        assert deliver.calls == 2
        assert waits == [2.0]
        (event,) = logger.events
        assert (event.event, event.outcome, event.reason) == (
            names.WEBHOOK_WORKER_FAILED,
            Outcome.ERROR,
            "worker_error",
        )
        assert "hunter2" not in repr(event)
