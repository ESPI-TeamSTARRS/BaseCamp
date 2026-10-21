from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.cancellation.domain.interfaces.cancellation_session import CancellationSession
from app.cancellation.domain.interfaces.cancellation_unit_of_work import CancellationUnitOfWork
from app.cancellation.infrastructure.repositories.sqlalchemy_cancellation_session import (
    SqlAlchemyCancellationSession,
)


class SqlAlchemyCancellationUnitOfWork(CancellationUnitOfWork):
    """Une seule transaction : verrou de l'intention puis nouvel état."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Iterator[CancellationSession]:
        with Session(self._engine) as session:
            try:
                yield SqlAlchemyCancellationSession(session)
                session.commit()
            except BaseException:
                session.rollback()
                raise
