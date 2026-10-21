from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from app.webhook.domain.interfaces.delivery_session import DeliverySession


class DeliveryUnitOfWork(ABC):
    @abstractmethod
    def begin(self) -> AbstractContextManager[DeliverySession]:
        """Ouvre une transaction : validée à la sortie du bloc, annulée si une exception survient."""
