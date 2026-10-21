from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.order.domain.errors.duplicate_idempotency_key_error import DuplicateIdempotencyKeyError
from app.order.domain.interfaces.order_unit_of_work import OrderUnitOfWork
from app.order.infrastructure.repositories.idempotency_violation import is_idempotency_violation
from app.order.infrastructure.repositories.sqlalchemy_order_repository import (
    SqlAlchemyOrderRepository,
)
from app.order.infrastructure.repositories.sqlalchemy_stock_ledger import SqlAlchemyStockLedger


class SqlAlchemyOrderUnitOfWork(OrderUnitOfWork):
    """Une transaction Postgres : verrous, commande et reservations valides ensemble ou pas du tout."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine)
        self.orders = SqlAlchemyOrderRepository(self._session)
        self.stock = SqlAlchemyStockLedger(self._session)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._session.rollback()  # sans effet apres un commit ; annule tout le reste
        self._session.close()

    def commit(self) -> None:
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            if is_idempotency_violation(error):
                raise DuplicateIdempotencyKeyError from None
            raise
