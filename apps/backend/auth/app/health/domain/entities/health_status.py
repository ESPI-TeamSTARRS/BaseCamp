from dataclasses import dataclass

from app.health.domain.enums.service_status import ServiceStatus


@dataclass(frozen=True)
class HealthStatus:
    service: str
    status: ServiceStatus

    def __post_init__(self) -> None:
        if not self.service.strip():
            raise ValueError("Le nom du service est obligatoire.")

    @property
    def is_up(self) -> bool:
        return self.status is ServiceStatus.UP
