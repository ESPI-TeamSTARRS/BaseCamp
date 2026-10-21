from abc import ABC, abstractmethod


class SecretHasher(ABC):
    @abstractmethod
    def hash(self, secret: str) -> str: ...

    @abstractmethod
    def verify(self, secret_hash: str, secret: str) -> bool:
        """Vérifie en temps constant; ne lève jamais d'exception (empreinte illisible : False)."""
