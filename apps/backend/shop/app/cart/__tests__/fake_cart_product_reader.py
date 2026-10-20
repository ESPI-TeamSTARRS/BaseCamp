"""Doublure du lecteur de produits pour les tests du panier (pas un test)."""

from collections.abc import Sequence

from app.cart.domain.entities.cart_product import CartProduct
from app.cart.domain.interfaces.cart_product_reader import CartProductReader


class FakeCartProductReader(CartProductReader):
    def __init__(self, products: list[CartProduct]) -> None:
        self._by_id = {p.id: p for p in products}

    def find_by_ids(self, product_ids: Sequence[str]) -> list[CartProduct]:
        return [self._by_id[i] for i in product_ids if i in self._by_id]


def default_catalog() -> list[CartProduct]:
    return [
        CartProduct(id="tente", name="Tente", price_cents=32900, stock=24),
        CartProduct(id="popote", name="Popote", price_cents=3900, stock=56),
        CartProduct(id="rare", name="Rare", price_cents=2000, stock=2),
        CartProduct(id="epuise", name="Epuise", price_cents=1500, stock=0),
    ]
