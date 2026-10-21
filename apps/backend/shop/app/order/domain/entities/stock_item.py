from dataclasses import dataclass


@dataclass(frozen=True)
class StockItem:
    """Produit verrouille pour la commande : prix en base (centimes) et stock courant."""

    product_id: str
    name: str
    price_cents: int
    stock: int
