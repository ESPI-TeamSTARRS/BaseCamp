import threading

from app.observability.domain.value_objects.request_key import RequestKey
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)

KEY = RequestKey(route="/payments/intents", method="POST", status=201)


class TestInProcessRequestMetrics:
    def test_a_fresh_instance_has_nothing_to_report(self) -> None:
        snapshot = InProcessRequestMetrics().snapshot()

        assert snapshot.requests == {}
        assert snapshot.latencies == {}

    def test_requests_are_counted_per_route_method_and_status(self) -> None:
        metrics = InProcessRequestMetrics()
        metrics.observe(KEY, 0.01)
        metrics.observe(KEY, 0.02)
        metrics.observe(RequestKey("/payments/intents", "POST", 422), 0.001)

        assert metrics.snapshot().requests == {
            KEY: 2,
            RequestKey("/payments/intents", "POST", 422): 1,
        }

    def test_latency_is_a_cumulative_histogram_per_route_and_method(self) -> None:
        metrics = InProcessRequestMetrics(bounds=(0.1, 1.0))
        metrics.observe(KEY, 0.05)
        metrics.observe(KEY, 0.5)
        metrics.observe(KEY, 5.0)

        distribution = metrics.snapshot().latencies[("/payments/intents", "POST")]

        assert distribution.bounds == (0.1, 1.0)
        assert distribution.cumulative_counts == (1, 2)
        assert distribution.count == 3
        assert distribution.total_seconds == 5.55

    def test_statuses_of_the_same_route_share_one_latency_distribution(self) -> None:
        metrics = InProcessRequestMetrics()
        metrics.observe(KEY, 0.01)
        metrics.observe(RequestKey("/payments/intents", "POST", 429), 0.01)

        assert list(metrics.snapshot().latencies) == [("/payments/intents", "POST")]
        assert metrics.snapshot().latencies[("/payments/intents", "POST")].count == 2

    def test_a_snapshot_is_a_copy_not_a_live_view(self) -> None:
        metrics = InProcessRequestMetrics()
        metrics.observe(KEY, 0.01)
        snapshot = metrics.snapshot()

        metrics.observe(KEY, 0.01)

        assert snapshot.requests[KEY] == 1

    def test_concurrent_observations_are_not_lost(self) -> None:
        metrics = InProcessRequestMetrics()

        def work() -> None:
            for _ in range(500):
                metrics.observe(KEY, 0.001)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert metrics.snapshot().requests[KEY] == 4000
