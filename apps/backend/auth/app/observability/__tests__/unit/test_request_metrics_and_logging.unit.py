from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.observability.application.record_request import RecordRequestUseCase
from app.observability.domain.value_objects.request_key import RequestKey
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)


class Setup:
    def __init__(self) -> None:
        self.metrics = InProcessRequestMetrics()
        self.events = InMemoryBusinessEventLogger()
        self.record = RecordRequestUseCase(self.metrics, self.events)


class TestMetrics:
    def test_requests_are_counted_per_route_method_and_status(self) -> None:
        setup = Setup()

        setup.record.execute("/login", "POST", 401, 0.02)
        setup.record.execute("/login", "POST", 401, 0.03)
        setup.record.execute("/login", "POST", 200, 0.1)

        snapshot = setup.metrics.snapshot()
        assert snapshot.requests == {
            RequestKey("/login", "POST", 401): 2,
            RequestKey("/login", "POST", 200): 1,
        }

    def test_latencies_fill_cumulative_buckets(self) -> None:
        setup = Setup()

        for seconds in (0.004, 0.02, 20.0):
            setup.record.execute("/me", "GET", 200, seconds)

        distribution = setup.metrics.snapshot().latencies[("/me", "GET")]
        assert distribution.count == 3
        assert distribution.cumulative_counts[0] == 1  # <= 5 ms
        assert distribution.cumulative_counts[-1] == 2  # <= 10 s, le 20 s deborde
        assert round(distribution.total_seconds, 3) == 20.024

    def test_an_unknown_route_and_an_odd_method_are_folded_into_fixed_labels(self) -> None:
        setup = Setup()

        setup.record.execute(None, "BREW", 404, 0.001)

        assert list(setup.metrics.snapshot().requests) == [RequestKey("unmatched", "OTHER", 404)]


class TestLines:
    def test_a_success_is_one_typed_info_line_with_route_status_and_latency(self) -> None:
        setup = Setup()

        setup.record.execute("/admin/users/{account_id}/disable", "POST", 200, 0.0151)

        [event] = setup.events.events
        assert (event.event, event.outcome, event.reason) == (
            "service.request_completed",
            Outcome.SUCCESS,
            None,
        )
        assert event.duration_ms == 15
        assert dict(event.attributes) == {
            "route": "/admin/users/{account_id}/disable",
            "method": "POST",
            "status": 200,
        }

    def test_client_and_server_errors_carry_their_status_as_the_reason(self) -> None:
        setup = Setup()

        setup.record.execute("/login", "POST", 429, 0.001)
        setup.record.execute("/login", "POST", 503, 0.001)

        assert [(e.outcome, e.reason) for e in setup.events.events] == [
            (Outcome.DENIED, "http_429"),
            (Outcome.ERROR, "http_503"),
        ]

    def test_successful_probes_are_counted_but_not_logged(self) -> None:
        setup = Setup()

        for route in ("/health", "/health/ready", "/metrics"):
            setup.record.execute(route, "GET", 200, 0.001)
        setup.record.execute("/health/ready", "GET", 503, 0.001)

        assert len(setup.metrics.snapshot().requests) == 4
        assert [e.reason for e in setup.events.events] == ["http_503"]

    def test_an_authenticated_caller_is_the_actor(self) -> None:
        setup = Setup()

        setup.record.execute("/me", "GET", 200, 0.001, "7f2a")

        [event] = setup.events.events
        assert (event.actor_type, event.actor_id) == ("user", "7f2a")
