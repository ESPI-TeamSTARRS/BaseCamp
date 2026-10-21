from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.payment_request.domain.interfaces.payable_orders import PayableOrders
from app.payment_request.domain.interfaces.payment_attempts import PaymentAttempts


class PaymentUnitOfWork(ABC):
    """Une transaction : commande verrouillée, tentatives et statut écrits ensemble ou pas du tout."""

    orders: PayableOrders
    attempts: PaymentAttempts

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
