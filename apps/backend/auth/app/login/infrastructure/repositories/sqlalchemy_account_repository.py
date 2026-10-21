from uuid import UUID

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from app.login.domain.entities.account import Account
from app.login.domain.interfaces.account_repository import AccountRepository
from app.login.infrastructure.mappers.account_mapper import AccountMapper
from app.login.infrastructure.models.account_model import AccountModel


class SqlAlchemyAccountRepository(AccountRepository):
    """Depot lie a la session (donc a la transaction) de l'unite de travail."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_email(self, email: str) -> Account | None:
        return self._find(AccountModel.email == email)

    def find_by_id(self, account_id: UUID) -> Account | None:
        return self._find(AccountModel.id == account_id)

    def update_password_hash(self, account_id: UUID, password_hash: str) -> None:
        self._session.execute(
            update(AccountModel)
            .where(AccountModel.id == account_id)
            .values(password_hash=password_hash)
        )

    def _find(self, condition: ColumnElement[bool]) -> Account | None:
        model = self._session.execute(select(AccountModel).where(condition)).scalar_one_or_none()
        return None if model is None else AccountMapper.to_entity(model)
