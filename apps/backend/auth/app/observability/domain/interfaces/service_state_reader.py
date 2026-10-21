from abc import ABC, abstractmethod
from datetime import datetime

from app.observability.domain.entities.service_state import ServiceState


class ServiceStateReader(ABC):
    """Lit l'etat metier a l'instant `now`; retourne None (sans lever) si la base est indisponible."""

    @abstractmethod
    def read(self, now: datetime) -> ServiceState | None: ...
