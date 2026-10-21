from abc import ABC, abstractmethod
from datetime import datetime

from app.service_token.domain.entities.rate_limit_decision import RateLimitDecision


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, client_id: str, now: datetime) -> RateLimitDecision:
        """Compte une demande pour ce client (compteur partagé, jamais en mémoire)."""
