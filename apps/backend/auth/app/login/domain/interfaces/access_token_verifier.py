from abc import ABC, abstractmethod
from datetime import datetime

from app.login.domain.entities.access_token_claims import AccessTokenClaims


class AccessTokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str, now: datetime) -> AccessTokenClaims:
        """Leve AccessTokenRejectedError (expire ou invalide) ; sinon les revendications."""
