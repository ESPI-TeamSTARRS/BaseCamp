from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.registration.domain.interfaces.user_repository import UserRepository
from app.registration.domain.interfaces.verification_token_repository import (
    VerificationTokenRepository,
)


class UnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    users: UserRepository
    tokens: VerificationTokenRepository

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
