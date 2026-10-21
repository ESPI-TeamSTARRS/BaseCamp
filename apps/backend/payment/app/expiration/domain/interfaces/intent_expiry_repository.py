from abc import ABC, abstractmethod
from datetime import datetime

from app.intent.domain.entities.payment_intent import PaymentIntent


class IntentExpiryRepository(ABC):
    @abstractmethod
    def expire_overdue(self, now: datetime, limit: int) -> list[PaymentIntent]:
        """Fait passer à `expired`, en une transaction, jusqu'à `limit` intentions en retard.

        Ne retient que les intentions encore `requires_confirmation` dont l'échéance est atteinte.
        Une intention verrouillée par une confirmation ou une annulation en cours est laissée de
        côté (elle sera reprise au passage suivant si elle attend toujours). Rend les intentions
        expirées par cet appel, jamais celles d'un appel précédent.
        """
