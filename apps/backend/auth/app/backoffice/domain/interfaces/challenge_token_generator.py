from abc import ABC, abstractmethod


class ChallengeTokenGenerator(ABC):
    @abstractmethod
    def generate(self) -> str:
        """Identifiant de defi opaque et aleatoire fort, remis une seule fois au client."""

    @abstractmethod
    def digest(self, token: str) -> str:
        """Empreinte deterministe stockee en base a la place de l'identifiant."""
