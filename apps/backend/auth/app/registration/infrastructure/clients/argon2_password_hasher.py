from argon2 import PasswordHasher as Argon2

from app.registration.domain.interfaces.password_hasher import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    """Argon2id avec les parametres par defaut d'argon2-cffi (profil RFC 9106 a memoire reduite)."""

    def __init__(self) -> None:
        self._argon2 = Argon2()

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)
