from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.registration.domain.entities.verification_token import VerificationToken


class VerificationTokenRepository(ABC):
    @abstractmethod
    def add(self, token: VerificationToken) -> None: ...

    @abstractmethod
    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        """Consomme atomiquement un jeton valide (usage unique) et rend son utilisateur."""
