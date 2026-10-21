from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from app.cancellation.domain.interfaces.cancellation_session import CancellationSession


class CancellationUnitOfWork(ABC):
    @abstractmethod
    def begin(self) -> AbstractContextManager[CancellationSession]:
        """Ouvre une transaction : validée à la sortie du bloc, annulée si une exception survient."""
