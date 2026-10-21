from app.observability.application.prometheus_text_formatter import PrometheusTextFormatter
from app.observability.domain.entities.request_metrics_snapshot import RequestMetricsSnapshot
from app.observability.domain.entities.service_state import ServiceState
from app.observability.domain.value_objects.latency_distribution import LatencyDistribution
from app.observability.domain.value_objects.request_key import RequestKey

STATE = ServiceState(
    intents_by_status={"requires_confirmation": 1, "succeeded": 4, "failed": 2},
    webhook_events_by_status={"pending": 3, "delivered": 9, "dead": 1},
    webhook_oldest_pending_age_seconds=42.5,
    captured_amount_cents=19960,
    refunded_amount_cents=4990,
    refunded_intents=1,
    ledger_discrepancies={"unbalanced_transaction": 0, "amount_mismatch": 2},
)
SNAPSHOT = RequestMetricsSnapshot(
    requests={RequestKey("/payments/intents", "POST", 201): 5},
    latencies={
        ("/payments/intents", "POST"): LatencyDistribution(
            bounds=(0.1, 1.0), cumulative_counts=(3, 5), count=6, total_seconds=7.25
        )
    },
)
EMPTY = RequestMetricsSnapshot(requests={}, latencies={})


def _lines(snapshot: RequestMetricsSnapshot, state: ServiceState | None) -> list[str]:
    return PrometheusTextFormatter().format(snapshot, state).splitlines()


class TestRequestSeries:
    def test_requests_are_a_counter_by_route_method_and_status(self) -> None:
        lines = _lines(SNAPSHOT, STATE)

        assert "# TYPE payment_http_requests_total counter" in lines
        assert (
            'payment_http_requests_total{route="/payments/intents",method="POST",status="201"} 5'
            in lines
        )

    def test_latency_is_a_histogram_with_inf_bucket_sum_and_count(self) -> None:
        lines = _lines(SNAPSHOT, STATE)

        assert "# TYPE payment_http_request_duration_seconds histogram" in lines
        labels = 'route="/payments/intents",method="POST"'
        bucket = f"payment_http_request_duration_seconds_bucket{{{labels}"
        assert f'{bucket},le="0.1"}} 3' in lines
        assert f'{bucket},le="1.0"}} 5' in lines
        assert f'{bucket},le="+Inf"}} 6' in lines
        assert f"payment_http_request_duration_seconds_sum{{{labels}}} 7.25" in lines
        assert f"payment_http_request_duration_seconds_count{{{labels}}} 6" in lines

    def test_without_traffic_the_series_are_declared_but_empty(self) -> None:
        lines = _lines(EMPTY, STATE)

        assert "# TYPE payment_http_requests_total counter" in lines
        assert not [line for line in lines if line.startswith("payment_http_requests_total{")]


class TestStateSeries:
    def test_intents_are_a_gauge_by_status(self) -> None:
        lines = _lines(EMPTY, STATE)

        assert "# TYPE payment_intents gauge" in lines
        assert 'payment_intents{status="succeeded"} 4' in lines
        assert 'payment_intents{status="requires_confirmation"} 1' in lines

    def test_webhook_events_and_the_age_of_the_oldest_pending_one(self) -> None:
        lines = _lines(EMPTY, STATE)

        assert 'payment_webhook_events{status="pending"} 3' in lines
        assert 'payment_webhook_events{status="dead"} 1' in lines
        assert "payment_webhook_oldest_pending_age_seconds 42.5" in lines

    def test_payments_and_refunds(self) -> None:
        lines = _lines(EMPTY, STATE)

        assert "payment_captured_amount_cents 19960" in lines
        assert "payment_refunded_amount_cents 4990" in lines
        assert "payment_refunded_intents 1" in lines

    def test_ledger_discrepancies_by_kind(self) -> None:
        lines = _lines(EMPTY, STATE)

        assert "# TYPE payment_ledger_discrepancies gauge" in lines
        assert 'payment_ledger_discrepancies{kind="unbalanced_transaction"} 0' in lines
        assert 'payment_ledger_discrepancies{kind="amount_mismatch"} 2' in lines

    def test_the_state_is_reported_up_when_it_was_read(self) -> None:
        assert "payment_state_up 1" in _lines(EMPTY, STATE)

    def test_when_the_database_is_unreachable_state_series_are_absent_and_state_is_down(
        self,
    ) -> None:
        lines = _lines(SNAPSHOT, None)

        assert "payment_state_up 0" in lines
        assert not [line for line in lines if line.startswith("payment_intents{")]
        assert not [line for line in lines if line.startswith("payment_ledger_discrepancies{")]
        assert any(line.startswith("payment_http_requests_total{") for line in lines)


class TestFormat:
    def test_every_family_has_help_and_type_before_its_samples(self) -> None:
        lines = _lines(SNAPSHOT, STATE)

        for family in ("payment_intents", "payment_http_requests_total", "payment_state_up"):
            help_at = lines.index(next(x for x in lines if x.startswith(f"# HELP {family} ")))
            type_at = lines.index(next(x for x in lines if x.startswith(f"# TYPE {family} ")))
            sample_at = lines.index(
                next(x for x in lines if not x.startswith("#") and x.startswith(family))
            )
            assert help_at < type_at < sample_at

    def test_the_output_ends_with_a_newline(self) -> None:
        assert PrometheusTextFormatter().format(EMPTY, STATE).endswith("\n")

    def test_label_values_are_escaped(self) -> None:
        snapshot = RequestMetricsSnapshot(
            requests={RequestKey('/a"b\\c\nd', "GET", 200): 1}, latencies={}
        )

        text = PrometheusTextFormatter().format(snapshot, None)

        assert 'route="/a\\"b\\\\c\\nd"' in text
