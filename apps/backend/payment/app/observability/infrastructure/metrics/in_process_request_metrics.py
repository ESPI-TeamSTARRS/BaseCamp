from bisect import bisect_left
from threading import Lock

from app.observability.domain.entities.request_metrics_snapshot import RequestMetricsSnapshot
from app.observability.domain.interfaces.request_metrics import RequestMetrics
from app.observability.domain.value_objects.latency_distribution import LatencyDistribution
from app.observability.domain.value_objects.request_key import RequestKey

DEFAULT_BOUNDS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class InProcessRequestMetrics(RequestMetrics):
    """Compteurs par processus, au format attendu par la collecte (qui agrège les instances).

    Ce n'est pas un état métier : perdre ces compteurs à un redémarrage est normal (la collecte
    gère un compteur qui repart de zéro). Le nombre de séries reste borné parce que les routes
    sont des gabarits (ou `unmatched`) et les méthodes une liste fermée.
    """

    def __init__(self, bounds: tuple[float, ...] = DEFAULT_BOUNDS) -> None:
        self._bounds = bounds
        self._lock = Lock()
        self._requests: dict[RequestKey, int] = {}
        # (route, méthode) -> (observations par borne non cumulées + débordement, [nombre, somme])
        self._latencies: dict[tuple[str, str], tuple[list[int], list[float]]] = {}

    def observe(self, key: RequestKey, seconds: float) -> None:
        slot = bisect_left(self._bounds, seconds)
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1
            buckets, totals = self._latencies.setdefault(
                (key.route, key.method), ([0] * (len(self._bounds) + 1), [0.0, 0.0])
            )
            buckets[slot] += 1
            totals[0] += 1
            totals[1] += seconds

    def snapshot(self) -> RequestMetricsSnapshot:
        with self._lock:
            requests = dict(self._requests)
            latencies = {
                series: self._distribution(buckets, totals)
                for series, (buckets, totals) in self._latencies.items()
            }
        return RequestMetricsSnapshot(requests=requests, latencies=latencies)

    def _distribution(self, buckets: list[int], totals: list[float]) -> LatencyDistribution:
        cumulative: list[int] = []
        running = 0
        for count in buckets[:-1]:
            running += count
            cumulative.append(running)
        return LatencyDistribution(
            bounds=self._bounds,
            cumulative_counts=tuple(cumulative),
            count=int(totals[0]),
            total_seconds=totals[1],
        )
