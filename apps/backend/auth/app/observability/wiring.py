from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.observability.application.observability_services import ObservabilityServices
from app.observability.application.record_request import RecordRequestUseCase
from app.observability.application.render_metrics import RenderMetricsUseCase
from app.observability.infrastructure.metrics.counting_event_logger import CountingEventLogger
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)
from app.observability.infrastructure.repositories.sqlalchemy_service_state_reader import (
    SqlAlchemyServiceStateReader,
)


@dataclass(frozen=True)
class Observability:
    """Journal compteur (a donner a toutes les tranches) et cas d'usage de l'observabilite."""

    events: BusinessEventLogger
    services: ObservabilityServices


def build_observability(
    engine: Engine, settings: Settings, journal: BusinessEventLogger
) -> Observability:
    """Assemble les compteurs du processus, le journal qui les alimente et la lecture d'etat."""
    metrics = InProcessRequestMetrics()
    events = CountingEventLogger(journal, metrics, settings.service_clients.keys())
    services = ObservabilityServices(
        record_request=RecordRequestUseCase(metrics, events),
        render_metrics=RenderMetricsUseCase(
            metrics, SqlAlchemyServiceStateReader(engine), lambda: datetime.now(UTC), events
        ),
    )
    return Observability(events, services)
