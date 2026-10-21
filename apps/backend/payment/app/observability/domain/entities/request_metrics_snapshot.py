from collections.abc import Mapping
from dataclasses import dataclass

from app.observability.domain.value_objects.latency_distribution import LatencyDistribution
from app.observability.domain.value_objects.request_key import RequestKey


@dataclass(frozen=True)
class RequestMetricsSnapshot:
    """Compteurs de requetes de ce processus : par (route, methode, statut) et durees par (route, methode)."""

    requests: Mapping[RequestKey, int]
    latencies: Mapping[tuple[str, str], LatencyDistribution]
