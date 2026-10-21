import uuid
from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.enums.order_status import OrderStatus
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway
from app.payment_request.application import payment_events
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.order_payment import OrderPayment
from app.payment_request.application.payment_order_not_found_error import (
    PaymentOrderNotFoundError,
)
from app.payment_request.domain.entities.payable_order import PayableOrder
from app.payment_request.domain.entities.payment_attempt import (
    REQUIRES_CONFIRMATION,
    PaymentAttempt,
)
from app.payment_request.domain.enums.payment_method import PaymentMethod
from app.payment_request.domain.interfaces.payment_unit_of_work import PaymentUnitOfWork

_METHODS = tuple(method.value for method in PaymentMethod)


class RequestOrderPaymentUseCase:
    """Demande l'intention de paiement d'une commande en attente : le total est celui figé en base."""

    def __init__(
        self,
        uow_factory: Callable[[], PaymentUnitOfWork],
        gateway: PaymentGateway,
        events: BusinessEventLogger,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._events = events

    def execute(self, order_id: str) -> OrderPayment:
        with self._uow_factory() as uow:
            order = self._payable_order(uow, order_id)
            attempts = uow.attempts.list_for_order(order.id)
            if attempts and attempts[-1].status == REQUIRES_CONFIRMATION:
                return self._replay(order, attempts[-1])
            attempt, intent = self._create(order, len(attempts) + 1)
            uow.attempts.add(attempt)
            uow.commit()
        self._events.log(
            BusinessEvent.success(
                payment_events.PAYMENT_REQUESTED,
                resource_type="order",
                resource_id=order.number,
                attributes={
                    "amount_cents": order.total_cents,
                    "currency": payment_events.CURRENCY,
                    "attempt": attempt.number,
                },
            )
        )
        return OrderPayment(order.number, intent, created=True, payment_methods=_METHODS)

    def _payable_order(self, uow: PaymentUnitOfWork, order_id: str) -> PayableOrder:
        order = uow.orders.find_for_update(order_id)
        if order is None:
            self._events.log(payment_events.rejected("order_not_found"))
            raise PaymentOrderNotFoundError
        reason = {
            OrderStatus.PAID: "order_already_paid",
            OrderStatus.EXPIRED: "order_expired",
            OrderStatus.REFUNDED: "order_already_paid",
        }.get(order.status)
        if reason is not None:
            self._events.log(payment_events.rejected(reason, order.number))
            raise OrderNotPayableError(reason)
        return order

    def _create(self, order: PayableOrder, number: int) -> tuple[PaymentAttempt, PaymentIntentRef]:
        reference = order.number if number == 1 else f"{order.number}-{number}"
        try:
            intent = self._gateway.create_intent(
                reference,
                order.total_cents,
                payment_events.CURRENCY,
                f"order-{order.number}-{number}",
            )
        except PaymentUnavailableError:
            self._events.log(payment_events.unavailable(order.number))
            raise
        attempt = PaymentAttempt(
            id=str(uuid.uuid4()),
            order_id=order.id,
            number=number,
            reference=reference,
            intent_id=intent.id,
            status=intent.status,
        )
        return attempt, intent

    def _replay(self, order: PayableOrder, attempt: PaymentAttempt) -> OrderPayment:
        intent = PaymentIntentRef(
            attempt.intent_id, attempt.status, order.total_cents, payment_events.CURRENCY
        )
        return OrderPayment(order.number, intent, created=False, payment_methods=_METHODS)
