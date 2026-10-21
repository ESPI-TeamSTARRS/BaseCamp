from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.order_expiration.__tests__.fakes import NOW, ExpirationStore, FakeExpirationUnitOfWork
from app.order_expiration.application.expire_unpaid_orders import ExpireUnpaidOrdersUseCase
from app.order_expiration.runner import run_forever, run_once


def _use_case(
    store: ExpirationStore, events: InMemoryBusinessEventLogger
) -> ExpireUnpaidOrdersUseCase:
    return ExpireUnpaidOrdersUseCase(
        lambda: FakeExpirationUnitOfWork(store), events, clock=lambda: NOW, ttl_minutes=30
    )


class _BrokenUseCase(ExpireUnpaidOrdersUseCase):
    def __init__(self) -> None:
        pass

    def execute(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("base arrêtée zz-secret-zz")


class TestRunner:
    def test_one_pass_expires_what_is_due_and_reports_success(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=45)
        events = InMemoryBusinessEventLogger()

        assert run_once(_use_case(store, events), events) is True
        assert store.orders["a1"].status == "expired"

    def test_a_failure_is_logged_without_the_exception_message_and_is_not_fatal(self) -> None:
        events = InMemoryBusinessEventLogger()

        assert run_once(_BrokenUseCase(), events) is False

        (event,) = events.events
        assert (event.event, event.outcome, event.reason) == (
            "order.expiration_failed",
            Outcome.ERROR,
            "expiration_error",
        )
        assert "zz-secret-zz" not in repr(event)

    def test_the_loop_runs_a_pass_then_sleeps_the_interval_until_asked_to_stop(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=45)
        events = InMemoryBusinessEventLogger()
        sleeps: list[float] = []
        passes = iter([False, False, True])

        run_forever(
            _use_case(store, events),
            events,
            interval_seconds=60,
            sleep=sleeps.append,
            should_stop=lambda: next(passes),
        )

        assert sleeps == [60, 60]
        assert store.orders["a1"].status == "expired"

    def test_the_loop_survives_failures(self) -> None:
        events = InMemoryBusinessEventLogger()
        remaining = iter([False, False, True])

        run_forever(
            _BrokenUseCase(),
            events,
            interval_seconds=1,
            sleep=lambda _: None,
            should_stop=lambda: next(remaining),
        )

        assert [e.event for e in events.events] == ["order.expiration_failed"] * 2
