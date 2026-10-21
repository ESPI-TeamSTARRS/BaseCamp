from abc import ABC, abstractmethod


class PasswordVerifier(ABC):
    @abstractmethod
    def verify(self, password_hash: str, password: str) -> bool: ...

    @abstractmethod
    def verify_decoy(self, password: str) -> None:
        """Verification factice au meme cout : un email inconnu ne se distingue pas par le temps."""

    @abstractmethod
    def needs_rehash(self, password_hash: str) -> bool:
        """Vrai si le hachage vient d'autres parametres que ceux en vigueur."""

    @abstractmethod
    def hash(self, password: str) -> str: ...
