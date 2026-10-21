from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.admin.domain.entities.account_page import AccountPage
from app.admin.domain.entities.managed_account import ManagedAccount


class AdminAccountRepository(ABC):
    @abstractmethod
    def list_page(self, limit: int, offset: int) -> AccountPage:
        """Comptes tries par date de creation puis identifiant, avec le total."""

    @abstractmethod
    def lock_operators(self) -> list[ManagedAccount]:
        """Operateurs actifs, lignes verrouillees jusqu'a la fin de la transaction.

        Deux desactivations simultanees se serialisent : la regle « jamais le dernier operateur
        actif » ne peut pas etre contournee par une course.
        """

    @abstractmethod
    def find_for_update(self, account_id: UUID) -> ManagedAccount | None: ...

    @abstractmethod
    def set_disabled(self, account_id: UUID, disabled_at: datetime | None) -> None: ...

    @abstractmethod
    def revoke_sessions(self, account_id: UUID) -> int:
        """Supprime tous les jetons de rafraichissement du compte; renvoie leur nombre."""

    @abstractmethod
    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        """Cree un compte `operator` (adresse consideree verifiee); `OperatorAlreadyExistsError`
        si l'adresse est deja prise."""
