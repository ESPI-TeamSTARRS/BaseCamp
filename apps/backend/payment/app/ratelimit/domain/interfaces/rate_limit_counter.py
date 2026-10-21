from abc import ABC, abstractmethod
from datetime import datetime


class RateLimitCounter(ABC):
    """Compteurs de requêtes par appelant, route et fenêtre, partagés entre les instances."""

    @abstractmethod
    def hit(self, caller: str, route: str, window_start: datetime) -> int:
        """Compte une requête de plus (atomique) et renvoie le total de la fenêtre."""

    @abstractmethod
    def purge_before(self, caller: str, route: str, before: datetime) -> None:
        """Supprime les fenêtres de cet appelant et de cette route antérieures à `before`."""
