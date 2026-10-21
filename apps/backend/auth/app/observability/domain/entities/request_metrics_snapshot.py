from collections.abc import Mapping
from dataclasses import dataclass

from app.observability.domain.value_objects.event_key import EventKey
from app.observability.domain.value_objects.latency_distribution import LatencyDistribution
from app.observability.domain.value_objects.request_key import RequestKey


@dataclass(frozen=True)
class RequestMetricsSnapshot:
    """Compteurs de ce processus : requetes par (route, methode, statut), durees par (route, methode)
    et evenements metier par (nom, resultat, motif, detail)."""

    requests: Mapping[RequestKey, int]
    latencies: Mapping[tuple[str, str], LatencyDistribution]
    events: Mapping[EventKey, int]
