from abc import ABC, abstractmethod
from contextlib import AbstractContextManager

from app.refund.domain.interfaces.refund_session import RefundSession


class RefundUnitOfWork(ABC):
    @abstractmethod
    def begin(self) -> AbstractContextManager[RefundSession]:
        """Ouvre une transaction : validée à la sortie du bloc, annulée si une exception survient."""
