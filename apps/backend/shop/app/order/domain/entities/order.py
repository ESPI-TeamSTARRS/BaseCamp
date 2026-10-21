from dataclasses import dataclass
from datetime import datetime

from app.cart.domain.services.shipping_policy import ShippingPolicy
from app.order.domain.entities.order_line import OrderLine
from app.order.domain.enums.order_status import OrderStatus
from app.order.domain.value_objects.shipping_address import ShippingAddress


@dataclass(frozen=True)
class Order:
    id: str
    number: str
    status: OrderStatus
    email: str
    address: ShippingAddress
    lines: tuple[OrderLine, ...]
    idempotency_key: str
    request_fingerprint: str
    created_at: datetime
    user_id: str | None = None

    @property
    def subtotal_cents(self) -> int:
        return sum(line.line_total_cents for line in self.lines)

    @property
    def shipping_cents(self) -> int:
        return ShippingPolicy.shipping_cents(self.subtotal_cents)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.shipping_cents
