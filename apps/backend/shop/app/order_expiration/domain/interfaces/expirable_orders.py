from abc import ABC, abstractmethod
from datetime import datetime

from app.order_expiration.domain.entities.expirable_order import ExpirableOrder
from app.order_expiration.domain.entities.released_line import ReleasedLine


class ExpirableOrders(ABC):
    @abstractmethod
    def find_expirable(self, created_before: datetime, limit: int) -> list[ExpirableOrder]:
        """Commandes encore en attente créées avant la date, verrouillées (les plus anciennes d'abord).

        Une commande déjà verrouillée par un paiement en cours est ignorée : elle sera revue au
        prochain passage si elle est toujours en attente.
        """

    @abstractmethod
    def expire(self, order_id: str) -> None:
        """Passe la commande à « expirée » (écrit au commit)."""

    @abstractmethod
    def release_reservations(self, order_id: str) -> list[ReleasedLine]:
        """Rend au stock les réservations encore actives de la commande et les marque libérées.

        Rejouer l'opération ne rend rien : seules les réservations « réservées » comptent.
        """
