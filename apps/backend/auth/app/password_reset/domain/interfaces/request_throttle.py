from abc import ABC, abstractmethod
from datetime import datetime


class RequestThrottle(ABC):
    """Limite par adresse (empreinte), sans etat en memoire du service."""

    @abstractmethod
    def allow(self, fingerprint: str, now: datetime) -> bool:
        """Enregistre la demande et rend True si le quota de la fenetre n'est pas depasse."""
