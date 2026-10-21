from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.admin.domain.interfaces.admin_account_repository import AdminAccountRepository


class AdminUnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    accounts: AdminAccountRepository

    @abstractmethod
    def __enter__(self) -> Self: ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...
