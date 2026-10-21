from abc import ABC, abstractmethod
from uuid import UUID

from app.webhook.domain.value_objects.delivery_result import DeliveryResult


class WebhookSender(ABC):
    """Envoie un événement signé à la boutique. Ne lève jamais : tout échec est un résultat."""

    @abstractmethod
    def send(self, event_id: UUID, body: str, signature: str) -> DeliveryResult: ...
