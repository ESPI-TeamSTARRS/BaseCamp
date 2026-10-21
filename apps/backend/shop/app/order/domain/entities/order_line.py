from dataclasses import dataclass


@dataclass(frozen=True)
class OrderLine:
    """Ligne figee a la commande : nom et prix unitaire (centimes) ne suivent plus le catalogue."""

    product_id: str
    product_name: str
    unit_price_cents: int
    quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity
