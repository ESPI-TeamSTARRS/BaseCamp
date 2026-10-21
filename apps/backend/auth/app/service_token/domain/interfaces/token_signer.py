from abc import ABC, abstractmethod

from app.service_token.domain.entities.token_claims import TokenClaims


class TokenSigner(ABC):
    @abstractmethod
    def sign(self, claims: TokenClaims) -> str: ...
