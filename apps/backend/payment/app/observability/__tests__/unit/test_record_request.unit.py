import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events import service_event_names as names
from app.core.events.outcome import Outcome
from app.observability.application.record_request import RecordRequestUseCase
from app.observability.domain.value_objects.request_key import RequestKey
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)


class Fixture:
    def __init__(self) -> None:
        self.metrics = InProcessRequestMetrics()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = RecordRequestUseCase(self.metrics, self.events)


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


class TestMetrics:
    def test_the_request_is_counted_with_its_route_template(self, fx: Fixture) -> None:
        fx.use_case.execute("/payments/intents/{intent_id}", "GET", 200, 0.02, "shop")

        assert fx.metrics.snapshot().requests == {
            RequestKey("/payments/intents/{intent_id}", "GET", 200): 1
        }

    def test_a_request_without_a_matched_route_is_labelled_unmatched(self, fx: Fixture) -> None:
        fx.use_case.execute(None, "GET", 404, 0.001, None)

        assert fx.metrics.snapshot().requests == {RequestKey("unmatched", "GET", 404): 1}

    def test_an_unusual_method_is_folded_so_labels_stay_bounded(self, fx: Fixture) -> None:
        fx.use_case.execute(None, 'FOO-BAR"\n', 405, 0.001, None)

        assert fx.metrics.snapshot().requests == {RequestKey("unmatched", "OTHER", 405): 1}

    def test_health_and_metrics_are_counted_too(self, fx: Fixture) -> None:
        fx.use_case.execute("/health", "GET", 200, 0.001, None)
        fx.use_case.execute("/metrics", "GET", 200, 0.01, None)

        assert {key.route for key in fx.metrics.snapshot().requests} == {"/health", "/metrics"}


class TestRequestEvent:
    def test_a_success_is_an_info_event_with_route_status_latency_and_caller(
        self, fx: Fixture
    ) -> None:
        fx.use_case.execute("/payments/intents", "POST", 201, 0.0123, "shop")

        (event,) = fx.events.events
        assert event.event == names.REQUEST_COMPLETED == "service.request_completed"
        assert event.outcome is Outcome.SUCCESS
        assert event.reason is None
        assert event.duration_ms == 12
        assert event.actor_type == "service"
        assert event.actor_id == "shop"
        assert dict(event.attributes) == {
            "route": "/payments/intents",
            "method": "POST",
            "status": 201,
        }

    def test_an_anonymous_request_has_no_actor(self, fx: Fixture) -> None:
        fx.use_case.execute("/payments/intents", "POST", 401, 0.001, None)

        (event,) = fx.events.events
        assert event.actor_type is None
        assert event.actor_id is None

    @pytest.mark.parametrize("status", [400, 401, 404, 409, 413, 422, 429])
    def test_a_client_error_is_a_denied_event(self, fx: Fixture, status: int) -> None:
        fx.use_case.execute("/payments/intents", "POST", status, 0.001, "shop")

        (event,) = fx.events.events
        assert event.outcome is Outcome.DENIED
        assert event.reason == f"http_{status}"

    @pytest.mark.parametrize("status", [500, 503, 504])
    def test_a_server_error_is_an_error_event(self, fx: Fixture, status: int) -> None:
        fx.use_case.execute("/payments/intents", "POST", status, 0.001, "shop")

        (event,) = fx.events.events
        assert event.outcome is Outcome.ERROR
        assert event.reason == f"http_{status}"

    @pytest.mark.parametrize("route", ["/health", "/health/ready", "/metrics"])
    def test_successful_probes_and_scrapes_are_not_logged(self, fx: Fixture, route: str) -> None:
        fx.use_case.execute(route, "GET", 200, 0.001, None)

        assert fx.events.events == []

    def test_a_failed_probe_is_still_logged(self, fx: Fixture) -> None:
        fx.use_case.execute("/health/ready", "GET", 503, 0.001, None)

        assert [event.reason for event in fx.events.events] == ["http_503"]
