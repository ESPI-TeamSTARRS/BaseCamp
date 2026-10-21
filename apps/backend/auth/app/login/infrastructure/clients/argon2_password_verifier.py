import secrets

from argon2 import PasswordHasher as Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from app.login.domain.interfaces.password_verifier import PasswordVerifier

DECOY_PASSWORD_BYTES = 16


class Argon2PasswordVerifier(PasswordVerifier):
    """Argon2id aux parametres courants (defauts d'argon2-cffi, comme l'inscription).

    Le hachage factice est produit avec ces memes parametres au demarrage : verifier un email
    inconnu coute donc autant qu'un mot de passe faux.
    """

    def __init__(self, argon2: Argon2 | None = None) -> None:
        self._argon2 = argon2 or Argon2()
        self._decoy_hash = self._argon2.hash(secrets.token_urlsafe(DECOY_PASSWORD_BYTES))

    @property
    def decoy_hash(self) -> str:
        return self._decoy_hash

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_decoy(self, password: str) -> None:
        self.verify(self._decoy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        try:
            return self._argon2.check_needs_rehash(password_hash)
        except InvalidHashError:
            return False

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)
