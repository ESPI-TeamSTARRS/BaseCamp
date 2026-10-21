import hashlib
import secrets

from app.registration.domain.interfaces.token_generator import TokenGenerator

TOKEN_BYTES = 32  # 256 bits d'entropie


class SecureTokenGenerator(TokenGenerator):
    def generate(self) -> str:
        return secrets.token_urlsafe(TOKEN_BYTES)

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
