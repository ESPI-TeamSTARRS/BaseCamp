from abc import ABC, abstractmethod
from uuid import UUID

from app.password_reset.domain.entities.resettable_account import ResettableAccount
from app.registration.domain.value_objects.email_address import EmailAddress


class AccountRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: EmailAddress) -> ResettableAccount | None: ...

    @abstractmethod
    def find_by_id(self, user_id: UUID) -> ResettableAccount | None: ...

    @abstractmethod
    def change_password(self, user_id: UUID, password_hash: str) -> None: ...
