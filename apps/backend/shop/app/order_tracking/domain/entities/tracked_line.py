from dataclasses import dataclass


@dataclass(frozen=True)
class TrackedLine:
    """Ligne telle que figée à la commande (nom et prix unitaire en centimes)."""

    name: str
    unit_price_cents: int
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity
