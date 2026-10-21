"""Doublures du paiement d'une commande : unité de travail en mémoire et passerelle enregistreuse."""

from dataclasses import dataclass, field, replace
from types import TracebackType
from typing import Self

from app.order.domain.enums.order_status import OrderStatus
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway
from app.payment_request.domain.entities.payable_order import PayableOrder
from app.payment_request.domain.entities.payment_attempt import PaymentAttempt
from app.payment_request.domain.interfaces.payable_orders import PayableOrders
from app.payment_request.domain.interfaces.payment_attempts import PaymentAttempts
from app.payment_request.domain.interfaces.payment_unit_of_work import PaymentUnitOfWork

ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"
OTHER_ORDER_ID = "9a7e44d8-1c1b-4e0e-b2f3-3f0d5a6b7c88"


@dataclass
class PaymentStore:
    orders: dict[str, PayableOrder] = field(default_factory=dict)
    attempts: list[PaymentAttempt] = field(default_factory=list)


def pending_order(order_id: str = ORDER_ID, total_cents: int = 4490) -> PayableOrder:
    return PayableOrder(
        id=order_id,
        number="BC-ABCDEFGHJK",
        status=OrderStatus.PENDING_PAYMENT,
        total_cents=total_cents,
    )


def store_with(status: OrderStatus = OrderStatus.PENDING_PAYMENT) -> PaymentStore:
    return PaymentStore(orders={ORDER_ID: replace(pending_order(), status=status)})


class _Orders(PayableOrders):
    def __init__(self, store: PaymentStore) -> None:
        self._store = store
        self.paid: list[str] = []

    def find_for_update(self, order_id: str) -> PayableOrder | None:
        return self._store.orders.get(order_id)

    def mark_paid(self, order_id: str) -> None:
        self.paid.append(order_id)


class _Attempts(PaymentAttempts):
    def __init__(self, store: PaymentStore) -> None:
        self._store = store
        self.added: list[PaymentAttempt] = []
        self.statuses: dict[str, str] = {}

    def list_for_order(self, order_id: str) -> list[PaymentAttempt]:
        return sorted(
            (a for a in self._store.attempts if a.order_id == order_id), key=lambda a: a.number
        )

    def add(self, attempt: PaymentAttempt) -> None:
        self.added.append(attempt)

    def set_status(self, attempt_id: str, status: str) -> None:
        self.statuses[attempt_id] = status


class FakePaymentUnitOfWork(PaymentUnitOfWork):
    orders: _Orders
    attempts: _Attempts

    def __init__(self, store: PaymentStore) -> None:
        self._store = store
        self.orders = _Orders(store)
        self.attempts = _Attempts(store)

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
        self._store.attempts.extend(self.attempts.added)
        for index, attempt in enumerate(self._store.attempts):
            if attempt.id in self.attempts.statuses:
                self._store.attempts[index] = replace(
                    attempt, status=self.attempts.statuses[attempt.id]
                )
        for order_id in self.orders.paid:
            self._store.orders[order_id] = replace(
                self._store.orders[order_id], status=OrderStatus.PAID
            )


class RecordingGateway(PaymentGateway):
    """Passerelle enregistreuse : le résultat de la confirmation dépend de la méthode de test."""

    def __init__(self, unavailable: bool = False) -> None:
        self.created: list[tuple[str, int, str, str]] = []
        self.confirmed: list[tuple[str, str, str]] = []
        self._unavailable = unavailable

    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        if self._unavailable:
            raise PaymentUnavailableError
        self.created.append((order_reference, amount_cents, currency, idempotency_key))
        return PaymentIntentRef(
            f"pi-{len(self.created)}", "requires_confirmation", amount_cents, currency
        )

    def get_intent(self, intent_id: str) -> PaymentIntentRef:
        raise NotImplementedError

    def confirm_intent(
        self, intent_id: str, payment_method: str, idempotency_key: str
    ) -> PaymentIntentRef:
        if self._unavailable:
            raise PaymentUnavailableError
        self.confirmed.append((intent_id, payment_method, idempotency_key))
        status = "succeeded" if payment_method == "pm_test_success" else "failed"
        return PaymentIntentRef(intent_id, status, 4490, "EUR")
