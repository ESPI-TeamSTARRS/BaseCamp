from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.registration.domain.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> None:
        """Leve EmailAlreadyRegisteredError si l'adresse existe (y compris en concurrence)."""

    @abstractmethod
    def mark_email_verified(self, user_id: UUID, now: datetime) -> None: ...
