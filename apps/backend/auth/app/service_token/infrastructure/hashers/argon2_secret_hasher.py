from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.service_token.domain.interfaces.secret_hasher import SecretHasher


class Argon2SecretHasher(SecretHasher):
    """Hachage argon2id (paramètres par défaut d'argon2-cffi : profil RFC 9106 faible mémoire)."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()

    def hash(self, secret: str) -> str:
        return self._hasher.hash(secret)

    def verify(self, secret_hash: str, secret: str) -> bool:
        try:
            return self._hasher.verify(secret_hash, secret)
        except (VerificationError, InvalidHashError):
            return False
