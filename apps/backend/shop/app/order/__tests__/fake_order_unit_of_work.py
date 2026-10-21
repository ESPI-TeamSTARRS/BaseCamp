"""Doublures en memoire de l'unite de travail des commandes (pas un test)."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from types import TracebackType
from typing import Self

from app.order.domain.entities.order import Order
from app.order.domain.entities.stock_item import StockItem
from app.order.domain.entities.stock_reservation import StockReservation
from app.order.domain.errors.duplicate_idempotency_key_error import DuplicateIdempotencyKeyError
from app.order.domain.interfaces.order_repository import OrderRepository
from app.order.domain.interfaces.order_unit_of_work import OrderUnitOfWork
from app.order.domain.interfaces.stock_ledger import StockLedger


@dataclass
class InMemoryStore:
    """Etat partage entre unites de travail : seul un commit y ecrit."""

    stock: dict[str, StockItem] = field(default_factory=dict)
    orders: dict[str, Order] = field(default_factory=dict)  # par cle d'idempotence
    reservations: list[StockReservation] = field(default_factory=list)
    concurrent_order: Order | None = None  # commande inseree par un autre processus au commit


class _Orders(OrderRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.pending: Order | None = None

    def find_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        return self._store.orders.get(idempotency_key)

    def add(self, order: Order) -> None:
        self.pending = order


class _Stock(StockLedger):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.working: dict[str, StockItem] = {}
        self.reserved: list[StockReservation] = []

    def lock_items(self, product_ids: Sequence[str]) -> list[StockItem]:
        found = [self._store.stock[i] for i in product_ids if i in self._store.stock]
        self.working.update({item.product_id: item for item in found})
        return found

    def reserve(self, order_id: str, product_id: str, quantity: int) -> None:
        item = self.working[product_id]
        self.working[product_id] = replace(item, stock=item.stock - quantity)
        self.reserved.append(StockReservation(order_id, product_id, quantity))


class FakeOrderUnitOfWork(OrderUnitOfWork):
    orders: _Orders
    stock: _Stock

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.orders = _Orders(store)
        self.stock = _Stock(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None  # sans commit, rien n'est ecrit : equivalent d'un rollback

    def commit(self) -> None:
        concurrent = self._store.concurrent_order
        if concurrent is not None:
            self._store.orders[concurrent.idempotency_key] = concurrent
            self._store.concurrent_order = None
            raise DuplicateIdempotencyKeyError
        pending = self.orders.pending
        if pending is not None:
            self._store.orders[pending.idempotency_key] = pending
        self._store.stock.update(self.stock.working)
        self._store.reservations.extend(self.stock.reserved)


class FakePseudonymizer:
    """Empreinte deterministe sans cle : suffit a verifier que l'email ne sort jamais en clair."""

    def pseudonymize(self, email: str) -> str:
        return "h-" + str(abs(hash(email.strip().lower())) % 10**8)


def default_stock() -> dict[str, StockItem]:
    items = [
        StockItem(product_id="tente", name="Tente", price_cents=32900, stock=24),
        StockItem(product_id="popote", name="Popote", price_cents=3900, stock=56),
        StockItem(product_id="rare", name="Rare", price_cents=2000, stock=2),
        StockItem(product_id="epuise", name="Epuise", price_cents=1500, stock=0),
    ]
    return {item.product_id: item for item in items}
