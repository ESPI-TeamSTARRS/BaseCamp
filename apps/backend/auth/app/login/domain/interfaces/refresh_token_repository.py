from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.login.domain.entities.refresh_token import RefreshToken


class RefreshTokenRepository(ABC):
    @abstractmethod
    def add(self, token: RefreshToken) -> None: ...

    @abstractmethod
    def consume(self, token_hash: str, now: datetime) -> RefreshToken | None:
        """Consomme atomiquement un jeton valide (ni utilise, ni expire); sinon `None`.

        Deux appels concurrents avec le meme jeton : un seul recoit le jeton.
        """

    @abstractmethod
    def find_by_hash(self, token_hash: str) -> RefreshToken | None: ...

    @abstractmethod
    def revoke_family(self, family_id: UUID) -> int:
        """Supprime tous les jetons de la famille; renvoie leur nombre."""
