from abc import ABC, abstractmethod

from app.service_token.domain.entities.token_claims import TokenClaims


class TokenDecoder(ABC):
    @abstractmethod
    def decode(self, token: str) -> TokenClaims:
        """Vérifie la signature (EdDSA seul) et lit les claims; lève InvalidTokenError sinon.

        L'expiration, l'émetteur, la nature et l'audience sont contrôlés par le cas d'usage.
        """
