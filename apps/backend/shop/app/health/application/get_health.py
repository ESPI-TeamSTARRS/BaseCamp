from app.health.domain.entities.health_status import HealthStatus
from app.health.domain.enums.service_status import ServiceStatus


class GetHealthUseCase:
    """Retourne l'etat du service (liveness)."""

    def __init__(self, service_name: str) -> None:
        self._service_name = service_name

    def execute(self) -> HealthStatus:
        return HealthStatus(service=self._service_name, status=ServiceStatus.UP)
