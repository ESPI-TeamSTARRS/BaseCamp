from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.observability.application.observability_services import ObservabilityServices
from app.observability.application.record_request import RecordRequestUseCase
from app.observability.application.render_metrics import RenderMetricsUseCase
from app.observability.infrastructure.metrics.in_process_request_metrics import (
    InProcessRequestMetrics,
)
from app.observability.infrastructure.repositories.sqlalchemy_service_state_reader import (
    SqlAlchemyServiceStateReader,
)


def build_observability_services(
    engine: Engine, settings: Settings, events: BusinessEventLogger
) -> ObservabilityServices:
    """Assemble les compteurs du processus et la lecture d'état en base (coût borné)."""
    metrics = InProcessRequestMetrics()
    reader = SqlAlchemyServiceStateReader(
        engine, timedelta(hours=settings.metrics_ledger_lookback_hours)
    )
    return ObservabilityServices(
        record_request=RecordRequestUseCase(metrics, events),
        render_metrics=RenderMetricsUseCase(metrics, reader, lambda: datetime.now(UTC), events),
    )
