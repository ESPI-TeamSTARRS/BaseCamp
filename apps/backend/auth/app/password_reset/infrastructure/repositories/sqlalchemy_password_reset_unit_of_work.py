from datetime import timedelta
from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.password_reset.domain.interfaces.password_reset_unit_of_work import (
    PasswordResetUnitOfWork,
)
from app.password_reset.infrastructure.repositories.sqlalchemy_account_repository import (
    SqlAlchemyAccountRepository,
)
from app.password_reset.infrastructure.repositories.sqlalchemy_request_throttle import (
    SqlAlchemyRequestThrottle,
)
from app.password_reset.infrastructure.repositories.sqlalchemy_reset_token_repository import (
    SqlAlchemyResetTokenRepository,
)
from app.password_reset.infrastructure.repositories.sqlalchemy_session_revoker import (
    SqlAlchemySessionRevoker,
)

MAX_REQUESTS_PER_ADDRESS = 3
THROTTLE_WINDOW = timedelta(hours=1)


class SqlAlchemyPasswordResetUnitOfWork(PasswordResetUnitOfWork):
    """Une session courte par transaction (aucun etat partage entre requetes)."""

    def __init__(
        self,
        engine: Engine,
        max_requests: int = MAX_REQUESTS_PER_ADDRESS,
        window: timedelta = THROTTLE_WINDOW,
    ) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.accounts = SqlAlchemyAccountRepository(self._session)
        self.tokens = SqlAlchemyResetTokenRepository(self._session)
        self.throttle = SqlAlchemyRequestThrottle(self._session, max_requests, window)
        self.sessions = SqlAlchemySessionRevoker(self._session)

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
