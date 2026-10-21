from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.registration.domain.entities.user import User
from app.registration.domain.exceptions.email_already_registered_error import (
    EmailAlreadyRegisteredError,
)
from app.registration.domain.interfaces.user_repository import UserRepository
from app.registration.infrastructure.mappers.user_mapper import UserMapper
from app.registration.infrastructure.models.user_model import UserModel


class SqlAlchemyUserRepository(UserRepository):
    """Depot lie a la session (donc a la transaction) de l'unite de travail."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> None:
        self._session.add(UserMapper.to_model(user))
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            raise EmailAlreadyRegisteredError from None

    def mark_email_verified(self, user_id: UUID, now: datetime) -> None:
        statement = (
            update(UserModel)
            .where(UserModel.id == user_id, UserModel.email_verified_at.is_(None))
            .values(email_verified_at=now)
        )
        self._session.execute(statement)
