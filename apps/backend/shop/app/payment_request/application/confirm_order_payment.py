from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.enums.order_status import OrderStatus
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway
from app.payment_request.application import payment_events
from app.payment_request.application.confirmed_payment import ConfirmedPayment
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.payment_order_not_found_error import (
    PaymentOrderNotFoundError,
)
from app.payment_request.domain.entities.payable_order import PayableOrder
from app.payment_request.domain.entities.payment_attempt import (
    FAILED,
    REQUIRES_CONFIRMATION,
    SUCCEEDED,
    PaymentAttempt,
)
from app.payment_request.domain.enums.payment_method import PaymentMethod
from app.payment_request.domain.interfaces.payment_unit_of_work import PaymentUnitOfWork

_REFUSALS = {OrderStatus.PAID: "order_already_paid", OrderStatus.EXPIRED: "order_expired"}


class ConfirmOrderPaymentUseCase:
    """Confirme la tentative en cours auprès du fournisseur; seul son résultat marque la commande payée."""

    def __init__(
        self,
        uow_factory: Callable[[], PaymentUnitOfWork],
        gateway: PaymentGateway,
        events: BusinessEventLogger,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._events = events

    def execute(self, order_id: str, payment_method: str) -> ConfirmedPayment:
        method = PaymentMethod(payment_method)
        with self._uow_factory() as uow:
            order = self._confirmable_order(uow, order_id)
            attempt = self._pending_attempt(uow, order)
            status = self._confirm(order, attempt, method)
            uow.attempts.set_status(attempt.id, status)
            if status == SUCCEEDED:
                uow.orders.mark_paid(order.id)
            uow.commit()
        self._emit_result(order, attempt, status)
        paid = status == SUCCEEDED
        return ConfirmedPayment(
            order.number, OrderStatus.PAID if paid else OrderStatus.PENDING_PAYMENT, status
        )

    def _confirmable_order(self, uow: PaymentUnitOfWork, order_id: str) -> PayableOrder:
        order = uow.orders.find_for_update(order_id)
        if order is None:
            self._events.log(payment_events.rejected("order_not_found"))
            raise PaymentOrderNotFoundError
        reason = _REFUSALS.get(order.status)
        if reason is not None:
            self._events.log(payment_events.rejected(reason, order.number))
            raise OrderNotPayableError(reason)
        return order

    def _pending_attempt(self, uow: PaymentUnitOfWork, order: PayableOrder) -> PaymentAttempt:
        attempts = uow.attempts.list_for_order(order.id)
        if not attempts or attempts[-1].status != REQUIRES_CONFIRMATION:
            self._events.log(payment_events.rejected("no_pending_payment", order.number))
            raise OrderNotPayableError("no_pending_payment")
        return attempts[-1]

    def _confirm(self, order: PayableOrder, attempt: PaymentAttempt, method: PaymentMethod) -> str:
        try:
            intent = self._gateway.confirm_intent(
                attempt.intent_id, method.value, f"confirm-{attempt.id}"
            )
        except PaymentUnavailableError:
            self._events.log(payment_events.unavailable(order.number))
            raise
        return SUCCEEDED if intent.status == SUCCEEDED else FAILED

    def _emit_result(self, order: PayableOrder, attempt: PaymentAttempt, status: str) -> None:
        if status == SUCCEEDED:
            self._events.log(
                BusinessEvent.success(
                    payment_events.ORDER_PAID,
                    resource_type="order",
                    resource_id=order.number,
                    attributes={
                        "amount_cents": order.total_cents,
                        "currency": payment_events.CURRENCY,
                        "attempt": attempt.number,
                    },
                )
            )
            return
        self._events.log(
            BusinessEvent.denied(
                payment_events.PAYMENT_FAILED,
                "provider_declined",
                resource_type="order",
                resource_id=order.number,
                attributes={"attempt": attempt.number},
            )
        )
