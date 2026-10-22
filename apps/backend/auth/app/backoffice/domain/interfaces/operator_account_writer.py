from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID


class OperatorAccountWriter(ABC):
    @abstractmethod
    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        """Cree le compte `operator` (adresse tenue pour verifiee : l'invitation la prouve).

        Leve `OperatorAlreadyExistsError` si l'adresse a deja un compte.
        """
