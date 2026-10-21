from dataclasses import replace

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.order.domain.enums.order_status import OrderStatus
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.payment_request.__tests__.fakes import (
    ORDER_ID,
    FakePaymentUnitOfWork,
    PaymentStore,
    RecordingGateway,
    store_with,
)
from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.payment_order_not_found_error import (
    PaymentOrderNotFoundError,
)
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.domain.enums.payment_method import PaymentMethod


class _Harness:
    def __init__(self, store: PaymentStore, gateway: RecordingGateway | None = None) -> None:
        self.store = store
        self.gateway = gateway or RecordingGateway()
        self.events = InMemoryBusinessEventLogger()
        factory = lambda: FakePaymentUnitOfWork(store)  # noqa: E731
        self.request = RequestOrderPaymentUseCase(factory, self.gateway, self.events)
        self.confirm = ConfirmOrderPaymentUseCase(factory, self.gateway, self.events)

    def names(self) -> list[str]:
        return [event.event for event in self.events.events]

    def clear(self) -> None:
        self.events.events.clear()


@pytest.fixture
def harness() -> _Harness:
    harness = _Harness(store_with())
    harness.request.execute(ORDER_ID)
    harness.clear()
    return harness


class TestConfirmOrderPayment:
    def test_a_successful_payment_marks_the_order_paid(self, harness: _Harness) -> None:
        result = harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        assert (result.order_status, result.payment_status) == (OrderStatus.PAID, "succeeded")
        assert harness.store.orders[ORDER_ID].status is OrderStatus.PAID
        assert harness.store.attempts[0].status == "succeeded"
        assert harness.gateway.confirmed[0][:2] == ("pi-1", "pm_test_success")
        assert harness.names() == ["order.paid"]
        event = harness.events.events[0]
        assert (event.outcome, event.resource_id) == (Outcome.SUCCESS, "BC-ABCDEFGHJK")
        assert event.attributes == {"amount_cents": 4490, "currency": "EUR", "attempt": 1}

    def test_a_declined_payment_keeps_the_order_pending_and_can_be_retried(
        self, harness: _Harness
    ) -> None:
        result = harness.confirm.execute(ORDER_ID, PaymentMethod.DECLINED)

        assert (result.order_status, result.payment_status) == (
            OrderStatus.PENDING_PAYMENT,
            "failed",
        )
        assert harness.store.orders[ORDER_ID].status is OrderStatus.PENDING_PAYMENT
        event = harness.events.events[0]
        assert (event.event, event.outcome, event.reason) == (
            "order.payment_failed",
            Outcome.DENIED,
            "provider_declined",
        )
        harness.request.execute(ORDER_ID)
        assert [a.number for a in harness.store.attempts] == [1, 2]

    def test_the_confirmation_key_is_stable_for_one_attempt(self, harness: _Harness) -> None:
        harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        attempt = harness.store.attempts[0]
        assert harness.gateway.confirmed[0][2] == f"confirm-{attempt.id}"

    @pytest.mark.parametrize(
        ("status", "reason"),
        [(OrderStatus.PAID, "order_already_paid"), (OrderStatus.EXPIRED, "order_expired")],
    )
    def test_a_payment_on_a_paid_or_expired_order_is_rejected_and_logged(
        self, harness: _Harness, status: OrderStatus, reason: str
    ) -> None:
        harness.store.orders[ORDER_ID] = replace(harness.store.orders[ORDER_ID], status=status)

        with pytest.raises(OrderNotPayableError) as error:
            harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        assert error.value.reason == reason
        assert harness.gateway.confirmed == []
        assert harness.names() == ["order.payment_rejected"]
        assert harness.events.events[0].reason == reason

    def test_without_a_pending_intent_nothing_can_be_confirmed(self) -> None:
        harness = _Harness(store_with())

        with pytest.raises(OrderNotPayableError) as error:
            harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        assert error.value.reason == "no_pending_payment"
        assert harness.names() == ["order.payment_rejected"]

    def test_an_unknown_order_is_refused(self) -> None:
        harness = _Harness(PaymentStore())

        with pytest.raises(PaymentOrderNotFoundError):
            harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        assert harness.events.events[0].reason == "order_not_found"

    def test_an_unavailable_provider_changes_nothing(self, harness: _Harness) -> None:
        harness.gateway._unavailable = True

        with pytest.raises(PaymentUnavailableError):
            harness.confirm.execute(ORDER_ID, PaymentMethod.SUCCESS)

        assert harness.store.orders[ORDER_ID].status is OrderStatus.PENDING_PAYMENT
        assert harness.store.attempts[0].status == "requires_confirmation"
        assert harness.names() == ["order.payment_unavailable"]
        assert harness.events.events[0].outcome is Outcome.ERROR
