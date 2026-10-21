from app.password_reset.domain.entities.password_reset_token import PasswordResetToken
from app.password_reset.infrastructure.models.password_reset_token_model import (
    PasswordResetTokenModel,
)


class PasswordResetTokenMapper:
    @staticmethod
    def to_model(token: PasswordResetToken) -> PasswordResetTokenModel:
        return PasswordResetTokenModel(
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
