import hashlib
import hmac
import secrets

_HASH_LENGTH = 16


class EmailPseudonymizer:
    """Empreinte stable d'un email (HMAC-SHA256 tronque) : correlable, jamais reversible."""

    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("a pseudonymization key is required")
        self._key = key.encode()

    def pseudonymize(self, email: str) -> str:
        digest = hmac.new(self._key, email.strip().lower().encode(), hashlib.sha256)
        return digest.hexdigest()[:_HASH_LENGTH]


def build_pseudonymizer(key: str) -> EmailPseudonymizer:
    """Sans cle (dev et local seulement), une cle ephemere : les empreintes changent a chaque demarrage."""
    return EmailPseudonymizer(key or secrets.token_hex(16))
