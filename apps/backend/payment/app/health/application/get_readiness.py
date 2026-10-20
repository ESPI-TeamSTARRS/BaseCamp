from app.health.domain.entities.health_status import HealthStatus
from app.health.domain.enums.service_status import ServiceStatus
from app.health.domain.interfaces.database_probe import DatabaseProbe


class GetReadinessUseCase:
    """Retourne l'etat de disponibilite du service (readiness) : la base doit repondre."""

    def __init__(self, service_name: str, database_probe: DatabaseProbe) -> None:
        self._service_name = service_name
        self._database_probe = database_probe

    def execute(self) -> HealthStatus:
        available = self._database_probe.is_available()
        status = ServiceStatus.UP if available else ServiceStatus.DOWN
        return HealthStatus(service=self._service_name, status=status)
