from dataclasses import dataclass

from app.cart.domain.enums.line_status import LineStatus


@dataclass(frozen=True)
class QuoteLine:
    product_id: str
    name: str
    unit_price_cents: int
    quantity: int
    available_quantity: int

    @property
    def line_total_cents(self) -> int:
        return self.unit_price_cents * self.quantity

    @property
    def status(self) -> LineStatus:
        if self.quantity > self.available_quantity:
            return LineStatus.INSUFFICIENT_STOCK
        return LineStatus.OK
