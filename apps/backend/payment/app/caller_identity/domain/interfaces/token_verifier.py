from abc import ABC, abstractmethod
from datetime import datetime

from app.caller_identity.domain.entities.caller import Caller


class TokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str, now: datetime) -> Caller:
        """Verifie signature, emetteur, audience (selon le type de jeton) et expiration.

        Un jeton de service doit viser `payment`; un jeton client, l'audience des clients.
        Leve `TokenRejectedError` ou `VerificationKeysUnavailableError`.
        """
