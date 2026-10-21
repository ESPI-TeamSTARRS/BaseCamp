from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.login.domain.entities.refresh_token import RefreshToken
from app.login.domain.interfaces.refresh_token_repository import RefreshTokenRepository
from app.login.infrastructure.mappers.refresh_token_mapper import RefreshTokenMapper
from app.login.infrastructure.models.refresh_token_model import RefreshTokenModel


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(RefreshTokenMapper.to_model(token))
        self._session.flush()

    def consume(self, token_hash: str, now: datetime) -> RefreshToken | None:
        """Un seul UPDATE conditionnel : de deux appels concurrents, un seul voit sa ligne."""
        statement = (
            update(RefreshTokenModel)
            .where(
                RefreshTokenModel.token_hash == token_hash,
                RefreshTokenModel.used_at.is_(None),
                RefreshTokenModel.expires_at > now,
            )
            .values(used_at=now)
            .returning(RefreshTokenModel)
            .execution_options(populate_existing=True)
        )
        model = self._session.execute(statement).scalar_one_or_none()
        return None if model is None else RefreshTokenMapper.to_entity(model)

    def find_by_hash(self, token_hash: str) -> RefreshToken | None:
        model = self._session.execute(
            select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        ).scalar_one_or_none()
        return None if model is None else RefreshTokenMapper.to_entity(model)

    def revoke_family(self, family_id: UUID) -> int:
        result = self._session.execute(
            delete(RefreshTokenModel).where(
                or_(RefreshTokenModel.family_id == family_id, RefreshTokenModel.id == family_id)
            )
        )
        self._session.flush()
        return int(result.rowcount)  # type: ignore[attr-defined]
