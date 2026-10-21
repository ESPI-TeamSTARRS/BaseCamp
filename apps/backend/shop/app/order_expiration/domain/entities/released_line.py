from dataclasses import dataclass


@dataclass(frozen=True)
class ReleasedLine:
    """Stock rendu au catalogue : produit et quantité réservée libérée."""

    product_id: str
    quantity: int
