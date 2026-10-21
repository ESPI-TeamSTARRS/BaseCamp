from abc import ABC, abstractmethod

from app.login.domain.entities.public_key import PublicKey


class PublicKeySet(ABC):
    @abstractmethod
    def public_keys(self) -> tuple[PublicKey, ...]:
        """Toutes les cles qui verifient des jetons encore valides (courante et anciennes)."""
