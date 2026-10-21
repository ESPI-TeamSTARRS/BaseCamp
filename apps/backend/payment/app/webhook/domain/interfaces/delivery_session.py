from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.webhook.domain.entities.outbox_event import OutboxEvent


class DeliverySession(ABC):
    """Une transaction de livraison : l'événement réservé reste verrouillé jusqu'à sa sortie."""

    @abstractmethod
    def claim_next_due(self, now: datetime) -> OutboxEvent | None:
        """Réserve le plus ancien événement `pending` échu, ignore ceux que d'autres traitent."""

    @abstractmethod
    def save(self, event: OutboxEvent) -> None: ...

    @abstractmethod
    def find_dead(self, event_id: UUID | None) -> list[OutboxEvent]:
        """Événements `dead` : celui désigné, ou tous si aucun identifiant n'est donné."""
