from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.payment_confirmation.domain.errors.duplicate_webhook_event_error import (
    DuplicateWebhookEventError,
)
from app.payment_confirmation.domain.interfaces.confirmation_unit_of_work import (
    ConfirmationUnitOfWork,
)
from app.payment_confirmation.infrastructure.repositories.sqlalchemy_settlement_targets import (
    SqlAlchemySettlementTargets,
)
from app.payment_confirmation.infrastructure.repositories.sqlalchemy_webhook_events import (
    SqlAlchemyWebhookEvents,
)


class SqlAlchemyConfirmationUnitOfWork(ConfirmationUnitOfWork):
    """Une transaction Postgres; la commande reste verrouillée jusqu'au commit ou à l'annulation."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine)
        self.events = SqlAlchemyWebhookEvents(self._session)
        self.targets = SqlAlchemySettlementTargets(self._session)

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
        try:
            self._session.commit()
        except IntegrityError:
            # Deux requêtes portant le même identifiant : la perdante n'a aucun effet (rejeu).
            self._session.rollback()
            raise DuplicateWebhookEventError from None
