from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.cart.domain.entities.cart_product import CartProduct


class CartProductReader(ABC):
    @abstractmethod
    def find_by_ids(self, product_ids: Sequence[str]) -> list[CartProduct]:
        """Produits existants parmi les identifiants demandes (les inconnus sont absents)."""
