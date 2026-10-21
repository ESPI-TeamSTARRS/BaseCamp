from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from app.confirmation.domain.interfaces.confirmation_session import ConfirmationSession


class ConfirmationUnitOfWork(ABC):
    @abstractmethod
    def begin(self) -> AbstractContextManager[ConfirmationSession]:
        """Ouvre une transaction : validée à la sortie du bloc, annulée si une exception survient."""
