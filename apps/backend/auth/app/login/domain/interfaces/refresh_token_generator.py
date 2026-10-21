from abc import ABC, abstractmethod


class RefreshTokenGenerator(ABC):
    @abstractmethod
    def generate(self) -> str:
        """Jeton opaque aleatoire fort, remis une seule fois au client."""

    @abstractmethod
    def digest(self, token: str) -> str:
        """Empreinte deterministe stockee en base a la place du jeton."""
