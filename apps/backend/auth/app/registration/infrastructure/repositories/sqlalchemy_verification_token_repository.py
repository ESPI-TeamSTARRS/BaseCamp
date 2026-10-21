from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.registration.domain.entities.verification_token import VerificationToken
from app.registration.domain.interfaces.verification_token_repository import (
    VerificationTokenRepository,
)
from app.registration.infrastructure.mappers.verification_token_mapper import (
    VerificationTokenMapper,
)
from app.registration.infrastructure.models.verification_token_model import (
    VerificationTokenModel,
)


class SqlAlchemyVerificationTokenRepository(VerificationTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: VerificationToken) -> None:
        self._session.add(VerificationTokenMapper.to_model(token))

    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        """Un seul UPDATE conditionnel : deux requetes simultanees ne le consomment jamais deux fois."""
        statement = (
            update(VerificationTokenModel)
            .where(
                VerificationTokenModel.token_hash == token_hash,
                VerificationTokenModel.used_at.is_(None),
                VerificationTokenModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(VerificationTokenModel.user_id)
        )
        return self._session.execute(statement).scalar_one_or_none()
