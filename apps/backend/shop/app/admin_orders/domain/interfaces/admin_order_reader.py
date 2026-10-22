from abc import ABC, abstractmethod

from app.admin_orders.domain.entities.admin_order import AdminOrder
from app.admin_orders.domain.entities.admin_order_page import AdminOrderPage


class AdminOrderReader(ABC):
    """Lecture seule : aucune methode d'ecriture n'existe sur ce port."""

    @abstractmethod
    def list_orders(
        self, status: str | None, search: str | None, limit: int, offset: int
    ) -> AdminOrderPage:
        """Commandes de tous les clients, les plus recentes d'abord; `search` = numero ou email."""

    @abstractmethod
    def find(self, order_id: str) -> AdminOrder | None:
        """La commande, ou `None` si l'identifiant est inconnu."""
