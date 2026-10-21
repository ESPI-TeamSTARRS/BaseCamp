from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.webhook.domain.interfaces.delivery_session import DeliverySession
from app.webhook.domain.interfaces.delivery_unit_of_work import DeliveryUnitOfWork
from app.webhook.infrastructure.repositories.sqlalchemy_delivery_session import (
    SqlAlchemyDeliverySession,
)


class SqlAlchemyDeliveryUnitOfWork(DeliveryUnitOfWork):
    """Une transaction par événement livré : le verrou est tenu pendant l'envoi."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Iterator[DeliverySession]:
        with Session(self._engine) as session:
            try:
                yield SqlAlchemyDeliverySession(session)
                session.commit()
            except BaseException:
                session.rollback()
                raise
