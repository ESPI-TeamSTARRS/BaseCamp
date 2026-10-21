from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.confirmation.domain.interfaces.confirmation_session import ConfirmationSession
from app.confirmation.domain.interfaces.confirmation_unit_of_work import ConfirmationUnitOfWork
from app.confirmation.infrastructure.repositories.sqlalchemy_confirmation_session import (
    SqlAlchemyConfirmationSession,
)
from app.ledger.infrastructure.repositories.sqlalchemy_ledger_repository import (
    SqlAlchemyLedgerRepository,
)


class SqlAlchemyConfirmationUnitOfWork(ConfirmationUnitOfWork):
    """Une seule transaction : verrou de l'intention, nouvel état, clé et grand livre."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Iterator[ConfirmationSession]:
        with Session(self._engine) as session:
            try:
                yield SqlAlchemyConfirmationSession(session, SqlAlchemyLedgerRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise
