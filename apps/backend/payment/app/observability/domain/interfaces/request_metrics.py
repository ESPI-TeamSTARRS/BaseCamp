from abc import ABC, abstractmethod

from app.observability.domain.entities.request_metrics_snapshot import RequestMetricsSnapshot
from app.observability.domain.value_objects.request_key import RequestKey


class RequestMetrics(ABC):
    """Compteurs de requetes du processus (la collecte agrege les instances)."""

    @abstractmethod
    def observe(self, key: RequestKey, seconds: float) -> None: ...

    @abstractmethod
    def snapshot(self) -> RequestMetricsSnapshot: ...
