from abc import ABC, abstractmethod
from datetime import datetime

from app.customer_identity.domain.entities.operator import Operator


class OperatorTokenVerifier(ABC):
    @abstractmethod
    def verify_operator(self, token: str, now: datetime) -> Operator:
        """Vérifie signature, émetteur, audience et expiration; renvoie l'identité et ses claims.

        Ne décide pas de l'accès (rôle, second facteur) : c'est le rôle du cas d'usage.
        Lève `ClientTokenRejectedError` ou `VerificationKeysUnavailableError`.
        """
