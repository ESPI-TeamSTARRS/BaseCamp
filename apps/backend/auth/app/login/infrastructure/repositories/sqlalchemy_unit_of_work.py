from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.login.domain.interfaces.unit_of_work import UnitOfWork
from app.login.infrastructure.repositories.sqlalchemy_account_repository import (
    SqlAlchemyAccountRepository,
)
from app.login.infrastructure.repositories.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Une session courte par transaction (aucun etat partage entre requetes)."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.accounts = SqlAlchemyAccountRepository(self._session)
        self.refresh_tokens = SqlAlchemyRefreshTokenRepository(self._session)

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
