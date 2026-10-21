from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.lockout.domain.interfaces.lockout_repository import LockoutRepository


class LockoutUnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    lockouts: LockoutRepository

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
