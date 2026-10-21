from abc import ABC, abstractmethod


class ServiceTokenProvider(ABC):
    """Fournit le jeton de service de `shop` pour appeler `payment` (emis par `auth`)."""

    @abstractmethod
    def token(self) -> str:
        """Jeton valide. Leve `PaymentUnavailableError` si `auth` n'en fournit aucun."""

    @abstractmethod
    def discard(self, token: str) -> None:
        """Oublie ce jeton (refuse par `payment`) : le prochain appel en demande un nouveau."""
