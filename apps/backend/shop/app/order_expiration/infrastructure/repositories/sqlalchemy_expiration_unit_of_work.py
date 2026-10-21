from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.order_expiration.domain.interfaces.expiration_unit_of_work import ExpirationUnitOfWork
from app.order_expiration.infrastructure.repositories.sqlalchemy_expirable_orders import (
    SqlAlchemyExpirableOrders,
)


class SqlAlchemyExpirationUnitOfWork(ExpirationUnitOfWork):
    """Une transaction Postgres par lot : commandes verrouillées jusqu'au commit ou à l'annulation."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine)
        self.orders = SqlAlchemyExpirableOrders(self._session)

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
