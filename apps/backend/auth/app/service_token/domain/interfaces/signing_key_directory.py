from abc import ABC, abstractmethod

from app.service_token.domain.entities.public_jwk import PublicJwk


class SigningKeyDirectory(ABC):
    @abstractmethod
    def public_jwk(self) -> PublicJwk: ...
