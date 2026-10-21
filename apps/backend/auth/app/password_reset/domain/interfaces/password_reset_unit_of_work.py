from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.password_reset.domain.interfaces.account_repository import AccountRepository
from app.password_reset.domain.interfaces.request_throttle import RequestThrottle
from app.password_reset.domain.interfaces.reset_token_repository import ResetTokenRepository
from app.password_reset.domain.interfaces.session_revoker import SessionRevoker


class PasswordResetUnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    accounts: AccountRepository
    tokens: ResetTokenRepository
    throttle: RequestThrottle
    sessions: SessionRevoker

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
