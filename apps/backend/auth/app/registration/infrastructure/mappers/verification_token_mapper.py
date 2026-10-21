from app.registration.domain.entities.verification_token import VerificationToken
from app.registration.infrastructure.models.verification_token_model import (
    VerificationTokenModel,
)


class VerificationTokenMapper:
    @staticmethod
    def to_model(token: VerificationToken) -> VerificationTokenModel:
        return VerificationTokenModel(
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
