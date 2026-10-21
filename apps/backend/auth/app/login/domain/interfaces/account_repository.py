from abc import ABC, abstractmethod
from uuid import UUID

from app.login.domain.entities.account import Account


class AccountRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: str) -> Account | None: ...

    @abstractmethod
    def find_by_id(self, account_id: UUID) -> Account | None: ...

    @abstractmethod
    def update_password_hash(self, account_id: UUID, password_hash: str) -> None: ...
