from sqlalchemy.orm import Session

from app.login.domain.entities.refresh_token import RefreshToken
from app.login.domain.interfaces.refresh_token_repository import RefreshTokenRepository
from app.login.infrastructure.mappers.refresh_token_mapper import RefreshTokenMapper


class SqlAlchemyRefreshTokenRepository(RefreshTokenRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(RefreshTokenMapper.to_model(token))
        self._session.flush()
