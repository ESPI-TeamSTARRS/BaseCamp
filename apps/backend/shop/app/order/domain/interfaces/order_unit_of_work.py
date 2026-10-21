from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.order.domain.interfaces.order_repository import OrderRepository
from app.order.domain.interfaces.stock_ledger import StockLedger


class OrderUnitOfWork(ABC):
    """Une transaction : tout est ecrit au commit, sinon annule en sortie de bloc."""

    orders: OrderRepository
    stock: StockLedger

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
    def commit(self) -> None:
        """Valide la transaction ; leve DuplicateIdempotencyKeyError si la cle existe deja."""
