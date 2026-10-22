from dataclasses import dataclass

from app.admin_orders.domain.entities.admin_order_summary import AdminOrderSummary


@dataclass(frozen=True)
class AdminOrderPage:
    items: tuple[AdminOrderSummary, ...]
    total: int
    limit: int
    offset: int
