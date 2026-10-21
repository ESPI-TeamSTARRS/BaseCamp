from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.password_reset.domain.entities.password_reset_token import PasswordResetToken
from app.password_reset.domain.interfaces.reset_token_repository import ResetTokenRepository
from app.password_reset.infrastructure.mappers.password_reset_token_mapper import (
    PasswordResetTokenMapper,
)
from app.password_reset.infrastructure.models.password_reset_token_model import (
    PasswordResetTokenModel,
)


class SqlAlchemyResetTokenRepository(ResetTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace(self, token: PasswordResetToken, now: datetime) -> None:
        self._session.execute(
            update(PasswordResetTokenModel)
            .where(
                PasswordResetTokenModel.user_id == token.user_id,
                PasswordResetTokenModel.used_at.is_(None),
            )
            .values(used_at=now)
        )
        self._session.add(PasswordResetTokenMapper.to_model(token))
        self._session.flush()

    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        """Un seul UPDATE conditionnel : deux requetes simultanees ne le consomment jamais deux fois."""
        statement = (
            update(PasswordResetTokenModel)
            .where(
                PasswordResetTokenModel.token_hash == token_hash,
                PasswordResetTokenModel.used_at.is_(None),
                PasswordResetTokenModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(PasswordResetTokenModel.user_id)
        )
        return self._session.execute(statement).scalar_one_or_none()
