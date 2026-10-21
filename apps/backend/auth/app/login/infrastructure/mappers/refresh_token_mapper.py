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
            family_id=token.family_id,
            used_at=token.used_at,
        )

    @staticmethod
    def to_entity(model: RefreshTokenModel) -> RefreshToken:
        """Une ligne anterieure a la rotation n'a pas de famille : elle forme la sienne."""
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            created_at=model.created_at,
            expires_at=model.expires_at,
            family_id=model.family_id or model.id,
            used_at=model.used_at,
        )
