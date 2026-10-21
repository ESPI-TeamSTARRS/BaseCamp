from abc import ABC, abstractmethod


class TokenGenerator(ABC):
    @abstractmethod
    def generate(self) -> str:
        """Jeton aleatoire fort, a n'envoyer qu'a son destinataire."""

    @abstractmethod
    def digest(self, token: str) -> str:
        """Empreinte deterministe stockee en base a la place du jeton."""
