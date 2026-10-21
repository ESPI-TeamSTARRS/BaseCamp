from dataclasses import dataclass

from app.observability.application.record_request import RecordRequestUseCase
from app.observability.application.render_metrics import RenderMetricsUseCase


@dataclass(frozen=True)
class ObservabilityServices:
    record_request: RecordRequestUseCase
    render_metrics: RenderMetricsUseCase
