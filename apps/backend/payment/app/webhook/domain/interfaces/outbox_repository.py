from abc import ABC, abstractmethod

from app.webhook.domain.entities.outbox_event import OutboxEvent


class OutboxRepository(ABC):
    @abstractmethod
    def add(self, event: OutboxEvent) -> None:
        """Ajoute l'événement dans la transaction en cours (celle du changement d'état)."""
