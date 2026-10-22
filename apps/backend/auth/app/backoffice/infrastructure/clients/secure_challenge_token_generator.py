import hashlib
import secrets

from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator

TOKEN_BYTES = 32  # 256 bits d'entropie


class SecureChallengeTokenGenerator(ChallengeTokenGenerator):
    def generate(self) -> str:
        return secrets.token_urlsafe(TOKEN_BYTES)

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
