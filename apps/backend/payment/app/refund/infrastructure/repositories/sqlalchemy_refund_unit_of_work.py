from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.ledger.infrastructure.repositories.sqlalchemy_ledger_repository import (
    SqlAlchemyLedgerRepository,
)
from app.refund.domain.interfaces.refund_session import RefundSession
from app.refund.domain.interfaces.refund_unit_of_work import RefundUnitOfWork
from app.refund.infrastructure.repositories.sqlalchemy_refund_session import (
    SqlAlchemyRefundSession,
)
from app.webhook.infrastructure.repositories.sqlalchemy_outbox_repository import (
    SqlAlchemyOutboxRepository,
)


class SqlAlchemyRefundUnitOfWork(RefundUnitOfWork):
    """Une seule transaction : verrou de l'intention, cumul, remboursement, grand livre et outbox."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def begin(self) -> Iterator[RefundSession]:
        with Session(self._engine) as session:
            try:
                yield SqlAlchemyRefundSession(
                    session,
                    SqlAlchemyLedgerRepository(session),
                    SqlAlchemyOutboxRepository(session),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise
