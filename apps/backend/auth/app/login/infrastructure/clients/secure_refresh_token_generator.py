import hashlib
import secrets

from app.login.domain.interfaces.refresh_token_generator import RefreshTokenGenerator

TOKEN_BYTES = 32  # 256 bits d'entropie


class SecureRefreshTokenGenerator(RefreshTokenGenerator):
    def generate(self) -> str:
        return secrets.token_urlsafe(TOKEN_BYTES)

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
