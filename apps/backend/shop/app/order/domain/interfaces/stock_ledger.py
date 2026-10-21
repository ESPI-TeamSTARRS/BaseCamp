from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.order.domain.entities.stock_item import StockItem


class StockLedger(ABC):
    @abstractmethod
    def lock_items(self, product_ids: Sequence[str]) -> list[StockItem]:
        """Verrouille (SELECT ... FOR UPDATE) les produits existants, dans un ordre stable."""

    @abstractmethod
    def reserve(self, order_id: str, product_id: str, quantity: int) -> None:
        """Retire la quantite du stock et enregistre la reservation de la commande."""
