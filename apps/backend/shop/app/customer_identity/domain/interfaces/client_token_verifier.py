from abc import ABC, abstractmethod
from datetime import datetime

from app.customer_identity.domain.entities.customer import Customer


class ClientTokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str, now: datetime) -> Customer:
        """Verifie signature, emetteur, audience et expiration; renvoie le client.

        Leve `ClientTokenRejectedError` (jeton refuse) ou `VerificationKeysUnavailableError`
        (aucune cle lisible : panne d'`auth` sans cle en cache).
        """
