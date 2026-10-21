from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.registration.domain.interfaces.unit_of_work import UnitOfWork
from app.registration.infrastructure.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from app.registration.infrastructure.repositories.sqlalchemy_verification_token_repository import (
    SqlAlchemyVerificationTokenRepository,
)


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Une session courte par transaction (aucun etat partage entre requetes)."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.users = SqlAlchemyUserRepository(self._session)
        self.tokens = SqlAlchemyVerificationTokenRepository(self._session)

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
