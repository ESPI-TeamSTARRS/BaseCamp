from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.login.domain.interfaces.account_repository import AccountRepository
from app.login.domain.interfaces.refresh_token_repository import RefreshTokenRepository


class UnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    accounts: AccountRepository
    refresh_tokens: RefreshTokenRepository

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
