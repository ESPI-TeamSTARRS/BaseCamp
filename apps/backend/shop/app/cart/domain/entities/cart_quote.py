from dataclasses import dataclass

from app.cart.domain.entities.quote_line import QuoteLine
from app.cart.domain.enums.line_status import LineStatus
from app.cart.domain.services.shipping_policy import ShippingPolicy


@dataclass(frozen=True)
class CartQuote:
    """Devis calcule par le serveur : seul lui decide des prix, de la livraison et du stock."""

    lines: tuple[QuoteLine, ...]

    @property
    def subtotal_cents(self) -> int:
        return sum(line.line_total_cents for line in self.lines)

    @property
    def shipping_cents(self) -> int:
        return ShippingPolicy.shipping_cents(self.subtotal_cents)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.shipping_cents

    @property
    def free_shipping_threshold_cents(self) -> int:
        return ShippingPolicy.FREE_SHIPPING_THRESHOLD_CENTS

    @property
    def amount_remaining_for_free_shipping_cents(self) -> int:
        return ShippingPolicy.amount_remaining_cents(self.subtotal_cents)

    @property
    def has_issues(self) -> bool:
        return any(line.status is LineStatus.INSUFFICIENT_STOCK for line in self.lines)
