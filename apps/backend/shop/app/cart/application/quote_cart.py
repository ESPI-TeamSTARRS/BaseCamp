from collections.abc import Sequence

from app.cart.application.invalid_cart_error import InvalidCartError
from app.cart.domain.entities.cart_quote import (
    CartQuote as CartQuote,  # re-export pour la presentation
)
from app.cart.domain.entities.quote_line import QuoteLine
from app.cart.domain.interfaces.cart_product_reader import CartProductReader

MAX_LINES = 50
MIN_QUANTITY = 1
MAX_QUANTITY = 10


class QuoteCartUseCase:
    """Devis d'un panier : prix et stock viennent de la base, jamais du client."""

    def __init__(self, reader: CartProductReader) -> None:
        self._reader = reader

    def execute(self, items: Sequence[tuple[str, int]]) -> CartQuote:
        self._validate(items)
        products = {p.id: p for p in self._reader.find_by_ids([pid for pid, _ in items])}
        if len(products) != len(items):
            raise InvalidCartError("Un ou plusieurs produits sont introuvables.")
        return CartQuote(
            lines=tuple(
                QuoteLine(
                    product_id=product_id,
                    name=products[product_id].name,
                    unit_price_cents=products[product_id].price_cents,
                    quantity=quantity,
                    available_quantity=products[product_id].stock,
                )
                for product_id, quantity in items
            )
        )

    @staticmethod
    def _validate(items: Sequence[tuple[str, int]]) -> None:
        if not 1 <= len(items) <= MAX_LINES:
            raise InvalidCartError("Le panier doit contenir entre 1 et 50 lignes.")
        if any(not MIN_QUANTITY <= quantity <= MAX_QUANTITY for _, quantity in items):
            raise InvalidCartError("Chaque quantite doit etre comprise entre 1 et 10.")
        if len({product_id for product_id, _ in items}) != len(items):
            raise InvalidCartError("Un produit ne peut figurer qu'une seule fois.")
