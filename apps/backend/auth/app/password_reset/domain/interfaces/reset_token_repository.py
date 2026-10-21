from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.password_reset.domain.entities.password_reset_token import PasswordResetToken


class ResetTokenRepository(ABC):
    @abstractmethod
    def replace(self, token: PasswordResetToken, now: datetime) -> None:
        """Invalide les jetons encore valides du compte puis enregistre le nouveau."""

    @abstractmethod
    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        """Consomme atomiquement un jeton valide (usage unique) et rend son utilisateur."""
