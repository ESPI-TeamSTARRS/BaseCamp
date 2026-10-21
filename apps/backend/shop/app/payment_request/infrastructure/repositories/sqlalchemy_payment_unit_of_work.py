from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.payment_request.domain.interfaces.payment_unit_of_work import PaymentUnitOfWork
from app.payment_request.infrastructure.repositories.sqlalchemy_payable_orders import (
    SqlAlchemyPayableOrders,
)
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_attempts import (
    SqlAlchemyPaymentAttempts,
)


class SqlAlchemyPaymentUnitOfWork(PaymentUnitOfWork):
    """Une transaction Postgres : la commande reste verrouillée jusqu'au commit ou à l'annulation."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine)
        self.orders = SqlAlchemyPayableOrders(self._session)
        self.attempts = SqlAlchemyPaymentAttempts(self._session)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._session.rollback()
        self._session.close()

    def commit(self) -> None:
        self._session.commit()
