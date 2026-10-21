from abc import ABC, abstractmethod

from app.login.domain.entities.access_token_claims import AccessTokenClaims


class AccessTokenSigner(ABC):
    @abstractmethod
    def sign(self, claims: AccessTokenClaims) -> str:
        """Jeton d'acces signe avec la cle de signature courante."""
