from dataclasses import dataclass

from app.order.domain.enums.order_status import OrderStatus


@dataclass(frozen=True)
class SettlementTarget:
    """La commande et la tentative visées par un événement (résolues par la référence de tentative)."""

    order_id: str
    order_number: str
    order_status: OrderStatus
    total_cents: int
    attempt_id: str
    attempt_status: str
