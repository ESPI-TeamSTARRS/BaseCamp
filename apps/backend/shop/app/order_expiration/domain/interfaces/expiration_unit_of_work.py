from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.order_expiration.domain.interfaces.expirable_orders import ExpirableOrders


class ExpirationUnitOfWork(ABC):
    """Une transaction par lot : statuts et stock sont écrits ensemble ou pas du tout."""

    orders: ExpirableOrders

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
