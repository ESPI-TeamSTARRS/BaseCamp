from abc import ABC, abstractmethod

from app.account_orders.domain.entities.account_order import AccountOrder
from app.account_orders.domain.entities.account_order_page import AccountOrderPage


class AccountOrderReader(ABC):
    @abstractmethod
    def list_for_user(self, user_id: str, limit: int, offset: int) -> AccountOrderPage:
        """Commandes de ce compte seulement, les plus recentes d'abord."""

    @abstractmethod
    def find_for_user(self, user_id: str, order_id: str) -> AccountOrder | None:
        """La commande si elle appartient a ce compte; `None` sinon (inconnue ou d'un autre compte)."""
