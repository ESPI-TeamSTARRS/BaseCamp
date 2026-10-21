from datetime import timedelta

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.order_expiration.__tests__.fakes import (
    NOW,
    ExpirationStore,
    FakeExpirationUnitOfWork,
)
from app.order_expiration.application.expire_unpaid_orders import ExpireUnpaidOrdersUseCase

TTL_MINUTES = 30


class _Harness:
    def __init__(self, store: ExpirationStore, batch_size: int = 100) -> None:
        self.store = store
        self.events = InMemoryBusinessEventLogger()
        self.clock_now = NOW
        self.use_case = ExpireUnpaidOrdersUseCase(
            lambda: FakeExpirationUnitOfWork(store),
            self.events,
            clock=lambda: self.clock_now,
            ttl_minutes=TTL_MINUTES,
            batch_size=batch_size,
        )


class TestExpireUnpaidOrders:
    def test_an_order_pending_for_more_than_the_delay_expires_and_gives_its_stock_back(
        self,
    ) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=31, lines=(("popote", 2), ("tente", 1)))
        harness = _Harness(store)

        report = harness.use_case.execute()

        assert store.orders["a1"].status == "expired"
        assert store.stock == {"popote": 0, "tente": 0}
        assert (report.expired_orders, report.released_units) == (1, 3)
        assert {r["status"] for r in store.reservations} == {"released"}

    def test_a_recent_order_is_left_alone(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=10)
        harness = _Harness(store)

        report = harness.use_case.execute()

        assert store.orders["a1"].status == "pending_payment"
        assert store.stock == {"popote": -2}
        assert report.expired_orders == 0

    def test_the_delay_is_strict_exactly_thirty_minutes_is_not_expired(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=30)
        store.add_order("a2", age_minutes=30.5)
        harness = _Harness(store)

        harness.use_case.execute()

        assert store.orders["a1"].status == "pending_payment"
        assert store.orders["a2"].status == "expired"

    def test_a_paid_order_is_never_expired(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=600, status="paid")
        harness = _Harness(store)

        harness.use_case.execute()

        assert store.orders["a1"].status == "paid"
        assert store.stock == {"popote": -2}

    def test_running_twice_gives_the_stock_back_only_once(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=45)
        harness = _Harness(store)

        harness.use_case.execute()
        second = harness.use_case.execute()

        assert store.stock == {"popote": 0}
        assert second.expired_orders == 0

    def test_the_clock_is_injected_an_order_expires_as_time_passes(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=20)
        harness = _Harness(store)
        harness.use_case.execute()
        assert store.orders["a1"].status == "pending_payment"

        harness.clock_now = NOW + timedelta(minutes=11)
        harness.use_case.execute()

        assert store.orders["a1"].status == "expired"

    def test_more_orders_than_a_batch_are_all_processed(self) -> None:
        store = ExpirationStore()
        for index in range(5):
            store.add_order(f"o{index}", age_minutes=40 + index)
        harness = _Harness(store, batch_size=2)

        report = harness.use_case.execute()

        assert report.expired_orders == 5
        assert all(o.status == "expired" for o in store.orders.values())

    def test_emits_one_event_per_expired_order_and_a_run_summary(self) -> None:
        store = ExpirationStore()
        store.add_order("a1", age_minutes=45, lines=(("popote", 2), ("tente", 1)))
        harness = _Harness(store)

        harness.use_case.execute()

        names = [event.event for event in harness.events.events]
        assert names == ["order.expired", "order.expiration_completed"]
        expired, summary = harness.events.events
        assert (expired.outcome, expired.resource_type, expired.resource_id) == (
            Outcome.SUCCESS,
            "order",
            "BC-A1",
        )
        assert expired.attributes == {"released_units": 3, "line_count": 2, "age_minutes": 45}
        assert summary.attributes == {"expired_orders": 1, "released_units": 3}

    def test_nothing_to_do_emits_nothing(self) -> None:
        harness = _Harness(ExpirationStore())

        harness.use_case.execute()

        assert harness.events.events == []

    def test_the_delay_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ExpireUnpaidOrdersUseCase(
                lambda: FakeExpirationUnitOfWork(ExpirationStore()),
                InMemoryBusinessEventLogger(),
                clock=lambda: NOW,
                ttl_minutes=0,
            )
