from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID


class FaceTemplateRepository(ABC):
    @abstractmethod
    def find(self, account_id: UUID) -> bytes | None:
        """Gabarit facial enrole de l'operateur, ou `None` s'il n'en a pas."""

    @abstractmethod
    def save(self, account_id: UUID, template: bytes, now: datetime) -> None:
        """Enregistre ou remplace le gabarit (l'enrolement par commande en depend)."""
