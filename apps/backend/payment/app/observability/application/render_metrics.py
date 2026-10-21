from collections.abc import Callable
from datetime import datetime

from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.observability.application.exceptions.metrics_not_exposed_error import (
    MetricsNotExposedError,
)
from app.observability.application.prometheus_text_formatter import PrometheusTextFormatter
from app.observability.domain.interfaces.request_metrics import RequestMetrics
from app.observability.domain.interfaces.service_state_reader import ServiceStateReader


class RenderMetricsUseCase:
    """Rend les métriques : compteurs du processus puis état métier lu en base à cet instant.

    Une demande passée par un proxy (la passerelle ajoute `X-Forwarded-*`) est refusée : la
    collecte est interne, jamais routée. Base indisponible : la réponse reste 200 avec
    `payment_state_up 0` et sans les séries d'état, pour que l'absence se voie.
    """

    def __init__(
        self,
        metrics: RequestMetrics,
        state_reader: ServiceStateReader,
        clock: Callable[[], datetime],
        events: BusinessEventLogger,
        formatter: PrometheusTextFormatter | None = None,
    ) -> None:
        self._metrics = metrics
        self._state_reader = state_reader
        self._clock = clock
        self._events = events
        self._formatter = formatter or PrometheusTextFormatter()

    def execute(self, proxied: bool) -> str:
        if proxied:
            self._events.log(BusinessEvent.denied(names.METRICS_REFUSED, "proxied_request"))
            raise MetricsNotExposedError
        state = self._state_reader.read(self._clock())
        return self._formatter.format(self._metrics.snapshot(), state)
