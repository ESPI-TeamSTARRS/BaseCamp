"""Doublures et fabriques de la consultation admin des commandes (pas des tests)."""

from datetime import UTC, datetime

from app.admin_orders.domain.entities.admin_order import AdminOrder
from app.admin_orders.domain.entities.admin_order_line import AdminOrderLine
from app.admin_orders.domain.entities.admin_order_page import AdminOrderPage
from app.admin_orders.domain.entities.admin_order_summary import AdminOrderSummary
from app.admin_orders.domain.entities.admin_shipping_address import AdminShippingAddress
from app.admin_orders.domain.interfaces.admin_order_reader import AdminOrderReader

EMAIL = "camille.martin@example.org"
ADDRESS_LINE = "12 rue des Alpes"


def make_order(order_id: str = "o-1", number: str = "BC-0001", status: str = "paid") -> AdminOrder:
    return AdminOrder(
        id=order_id,
        number=number,
        status=status,
        email=EMAIL,
        shipping_address=AdminShippingAddress(
            full_name="Camille Martin",
            line1=ADDRESS_LINE,
            line2=None,
            postal_code="38000",
            city="Grenoble",
            country="FR",
        ),
        lines=(AdminOrderLine("Popote", 3900, 2),),
        subtotal_cents=7800,
        shipping_cents=490,
        total_cents=8290,
        created_at=datetime(2026, 10, 22, 8, 0, tzinfo=UTC),
    )


class StubAdminOrderReader(AdminOrderReader):
    def __init__(self, *orders: AdminOrder) -> None:
        self.orders = list(orders)
        self.queries: list[tuple[str | None, str | None, int, int]] = []

    def list_orders(
        self, status: str | None, search: str | None, limit: int, offset: int
    ) -> AdminOrderPage:
        self.queries.append((status, search, limit, offset))
        items = tuple(
            AdminOrderSummary(o.id, o.number, o.status, o.email, o.total_cents, 2, o.created_at)
            for o in self.orders
        )
        return AdminOrderPage(items=items, total=len(items), limit=limit, offset=offset)

    def find(self, order_id: str) -> AdminOrder | None:
        return next((o for o in self.orders if o.id == order_id), None)
