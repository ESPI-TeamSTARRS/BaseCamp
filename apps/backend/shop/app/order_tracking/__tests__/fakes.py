"""Doublure du lecteur de commandes pour le suivi (pas un test)."""

from datetime import UTC, datetime

from app.order_tracking.domain.entities.tracked_line import TrackedLine
from app.order_tracking.domain.entities.tracked_order import TrackedOrder
from app.order_tracking.domain.interfaces.tracked_order_reader import TrackedOrderReader

NUMBER = "BC-ABCDEFGHJK"
EMAIL = "camille.martin@example.org"


def tracked_order(status: str = "pending_payment", email: str = EMAIL) -> TrackedOrder:
    return TrackedOrder(
        number=NUMBER,
        email=email,
        status=status,
        lines=(TrackedLine(name="Popote", unit_price_cents=3900, quantity=2),),
        subtotal_cents=7800,
        shipping_cents=0,
        total_cents=7800,
        created_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
    )


class FakeTrackedOrderReader(TrackedOrderReader):
    def __init__(self, *orders: TrackedOrder) -> None:
        self._orders = {order.number: order for order in orders}
        self.lookups: list[str] = []

    def find_by_number(self, number: str) -> TrackedOrder | None:
        self.lookups.append(number)
        return self._orders.get(number)
