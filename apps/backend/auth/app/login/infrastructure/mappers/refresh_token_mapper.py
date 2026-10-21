from app.login.domain.entities.refresh_token import RefreshToken
from app.login.infrastructure.models.refresh_token_model import RefreshTokenModel


class RefreshTokenMapper:
    @staticmethod
    def to_model(token: RefreshToken) -> RefreshTokenModel:
        return RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            created_at=token.created_at,
            expires_at=token.expires_at,
        )
