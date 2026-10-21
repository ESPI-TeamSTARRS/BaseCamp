"""Doublures de l'expiration : stock, commandes et réservations en mémoire (pas un test)."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self

from app.order_expiration.domain.entities.expirable_order import ExpirableOrder
from app.order_expiration.domain.entities.released_line import ReleasedLine
from app.order_expiration.domain.interfaces.expirable_orders import ExpirableOrders
from app.order_expiration.domain.interfaces.expiration_unit_of_work import ExpirationUnitOfWork

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


@dataclass
class StoredOrder:
    id: str
    number: str
    status: str
    created_at: datetime


@dataclass
class ExpirationStore:
    orders: dict[str, StoredOrder] = field(default_factory=dict)
    reservations: list[dict[str, object]] = field(
        default_factory=list
    )  # order_id, product_id, quantity, status
    stock: dict[str, int] = field(default_factory=dict)

    def add_order(
        self,
        order_id: str,
        age_minutes: float,
        status: str = "pending_payment",
        lines: tuple[tuple[str, int], ...] = (("popote", 2),),
    ) -> None:
        self.orders[order_id] = StoredOrder(
            order_id, f"BC-{order_id.upper()}", status, NOW - timedelta(minutes=age_minutes)
        )
        for product_id, quantity in lines:
            self.reservations.append(
                {
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "status": "reserved",
                }
            )
            self.stock[product_id] = self.stock.get(product_id, 0) - quantity


class _Orders(ExpirableOrders):
    def __init__(self, store: ExpirationStore) -> None:
        self._store = store
        self.expired: list[str] = []
        self.released: list[tuple[str, str, int]] = []

    def find_expirable(self, created_before: datetime, limit: int) -> list[ExpirableOrder]:
        found = sorted(
            (
                o
                for o in self._store.orders.values()
                if o.status == "pending_payment" and o.created_at < created_before
            ),
            key=lambda o: o.created_at,
        )
        return [ExpirableOrder(o.id, o.number, o.created_at) for o in found[:limit]]

    def expire(self, order_id: str) -> None:
        self.expired.append(order_id)

    def release_reservations(self, order_id: str) -> list[ReleasedLine]:
        lines = [
            ReleasedLine(str(r["product_id"]), int(r["quantity"]))  # type: ignore[call-overload]
            for r in self._store.reservations
            if r["order_id"] == order_id and r["status"] == "reserved"
        ]
        self.released.extend((order_id, line.product_id, line.quantity) for line in lines)
        return lines


class FakeExpirationUnitOfWork(ExpirationUnitOfWork):
    orders: _Orders

    def __init__(self, store: ExpirationStore) -> None:
        self._store = store
        self.orders = _Orders(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        for order_id in self.orders.expired:
            self._store.orders[order_id] = replace(self._store.orders[order_id], status="expired")
        for order_id, product_id, quantity in self.orders.released:
            self._store.stock[product_id] = self._store.stock.get(product_id, 0) + quantity
            for reservation in self._store.reservations:
                if reservation["order_id"] == order_id and reservation["product_id"] == product_id:
                    reservation["status"] = "released"
