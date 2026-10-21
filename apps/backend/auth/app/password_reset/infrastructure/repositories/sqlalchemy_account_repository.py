from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.password_reset.domain.entities.resettable_account import ResettableAccount
from app.password_reset.domain.interfaces.account_repository import AccountRepository
from app.password_reset.infrastructure.mappers.resettable_account_mapper import (
    ResettableAccountMapper,
)
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.models.user_model import UserModel


class SqlAlchemyAccountRepository(AccountRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_email(self, email: EmailAddress) -> ResettableAccount | None:
        model = self._session.execute(
            select(UserModel).where(UserModel.email == email.value)
        ).scalar_one_or_none()
        return None if model is None else ResettableAccountMapper.to_entity(model)

    def find_by_id(self, user_id: UUID) -> ResettableAccount | None:
        model = self._session.get(UserModel, user_id)
        return None if model is None else ResettableAccountMapper.to_entity(model)

    def change_password(self, user_id: UUID, password_hash: str) -> None:
        self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(password_hash=password_hash)
        )
