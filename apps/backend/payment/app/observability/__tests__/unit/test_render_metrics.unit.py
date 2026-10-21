from datetime import UTC, datetime

import pytest
from app.observability.application.exceptions.metrics_not_exposed_error import (
    MetricsNotExposedError,
)
from app.observability.application.render_metrics import RenderMetricsUseCase
from app.observability.domain.entities.service_state import ServiceState
from app.observability.domain.interfaces.service_state_reader import ServiceStateReader
from app.observability.domain.value_objects.request_key import RequestKey
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events import service_event_names as names
from app.core.events.outcome import Outcome

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
STATE = ServiceState(
    intents_by_status={"succeeded": 2},
    webhook_events_by_status={"pending": 1},
    webhook_oldest_pending_age_seconds=3.0,
    captured_amount_cents=100,
    refunded_amount_cents=0,
    refunded_intents=0,
    ledger_discrepancies={"amount_mismatch": 0},
)


class FakeStateReader(ServiceStateReader):
    def __init__(self, state: ServiceState | None) -> None:
        self._state = state
        self.reads: list[datetime] = []

    def read(self, now: datetime) -> ServiceState | None:
        self.reads.append(now)
        return self._state


class Fixture:
    def __init__(self, state: ServiceState | None = STATE) -> None:
        self.metrics = InProcessRequestMetrics()
        self.reader = FakeStateReader(state)
        self.events = InMemoryBusinessEventLogger()
        self.use_case = RenderMetricsUseCase(self.metrics, self.reader, lambda: NOW, self.events)


class TestRender:
    def test_it_renders_the_process_counters_and_the_state_read_now(self) -> None:
        fx = Fixture()
        fx.metrics.observe(RequestKey("/payments/intents", "POST", 201), 0.01)

        text = fx.use_case.execute(proxied=False)

        assert (
            'payment_http_requests_total{route="/payments/intents",method="POST",status="201"} 1'
            in text
        )
        assert 'payment_intents{status="succeeded"} 2' in text
        assert fx.reader.reads == [NOW]

    def test_an_unreachable_database_still_answers_with_the_state_down(self) -> None:
        fx = Fixture(state=None)

        text = fx.use_case.execute(proxied=False)

        assert "payment_state_up 0" in text

    def test_a_scrape_is_not_logged(self) -> None:
        fx = Fixture()

        fx.use_case.execute(proxied=False)

        assert fx.events.events == []


class TestRefusal:
    def test_a_request_that_came_through_a_proxy_is_refused_and_logged(self) -> None:
        fx = Fixture()

        with pytest.raises(MetricsNotExposedError):
            fx.use_case.execute(proxied=True)

        (event,) = fx.events.events
        assert event.event == names.METRICS_REFUSED == "service.metrics_refused"
        assert event.outcome is Outcome.DENIED
        assert event.reason == "proxied_request"

    def test_a_refused_request_does_not_touch_the_database(self) -> None:
        fx = Fixture()

        with pytest.raises(MetricsNotExposedError):
            fx.use_case.execute(proxied=True)

        assert fx.reader.reads == []
