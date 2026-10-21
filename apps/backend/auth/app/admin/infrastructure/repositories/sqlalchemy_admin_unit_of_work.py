from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.admin.domain.interfaces.admin_unit_of_work import AdminUnitOfWork
from app.admin.infrastructure.repositories.sqlalchemy_admin_account_repository import (
    SqlAlchemyAdminAccountRepository,
)


class SqlAlchemyAdminUnitOfWork(AdminUnitOfWork):
    """Une session courte par transaction (aucun etat partage entre requetes)."""

    def __init__(self, engine: Engine) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.accounts = SqlAlchemyAdminAccountRepository(self._session)

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
