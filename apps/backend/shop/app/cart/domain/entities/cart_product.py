from dataclasses import dataclass


@dataclass(frozen=True)
class CartProduct:
    """Ce que le devis sait d'un produit : prix en base (centimes) et stock disponible."""

    id: str
    name: str
    price_cents: int
    stock: int
