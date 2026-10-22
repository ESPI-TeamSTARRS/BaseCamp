from dataclasses import dataclass


@dataclass(frozen=True)
class AdminOrderLine:
    """Ligne telle que figee a la commande (nom et prix unitaire en centimes)."""

    name: str
    unit_price_cents: int
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity
