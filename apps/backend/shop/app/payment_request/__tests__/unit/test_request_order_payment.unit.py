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
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.payment_order_not_found_error import (
    PaymentOrderNotFoundError,
)
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.domain.entities.payment_attempt import PaymentAttempt


class _Harness:
    def __init__(self, store: PaymentStore, gateway: RecordingGateway | None = None) -> None:
        self.store = store
        self.gateway = gateway or RecordingGateway()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = RequestOrderPaymentUseCase(
            lambda: FakePaymentUnitOfWork(store), self.gateway, self.events
        )

    def names(self) -> list[str]:
        return [event.event for event in self.events.events]


def _attempt(number: int, status: str) -> PaymentAttempt:
    return PaymentAttempt(
        id=f"att-{number}",
        order_id=ORDER_ID,
        number=number,
        reference="BC-ABCDEFGHJK" if number == 1 else f"BC-ABCDEFGHJK-{number}",
        intent_id=f"pi-old-{number}",
        status=status,
    )


class TestRequestOrderPayment:
    def test_asks_the_provider_for_an_intent_with_the_server_side_total(self) -> None:
        harness = _Harness(store_with())

        payment = harness.use_case.execute(ORDER_ID)

        assert harness.gateway.created == [("BC-ABCDEFGHJK", 4490, "EUR", "order-BC-ABCDEFGHJK-1")]
        assert payment.created is True
        assert payment.order_number == "BC-ABCDEFGHJK"
        assert (payment.intent.status, payment.intent.amount_cents) == (
            "requires_confirmation",
            4490,
        )
        assert [a.intent_id for a in harness.store.attempts] == [payment.intent.id]
        assert harness.store.attempts[0].reference == "BC-ABCDEFGHJK"

    def test_replaying_while_an_intent_awaits_confirmation_creates_nothing_new(self) -> None:
        store = store_with()
        harness = _Harness(store)
        first = harness.use_case.execute(ORDER_ID)

        second = harness.use_case.execute(ORDER_ID)

        assert second.created is False
        assert second.intent.id == first.intent.id
        assert len(harness.gateway.created) == 1
        assert len(store.attempts) == 1

    def test_a_new_intent_with_a_new_reference_is_created_after_a_failed_attempt(self) -> None:
        store = store_with()
        store.attempts.append(_attempt(1, "failed"))
        harness = _Harness(store)

        payment = harness.use_case.execute(ORDER_ID)

        assert payment.created is True
        assert harness.gateway.created == [
            ("BC-ABCDEFGHJK-2", 4490, "EUR", "order-BC-ABCDEFGHJK-2")
        ]
        assert [a.number for a in store.attempts] == [1, 2]

    @pytest.mark.parametrize(
        ("status", "reason"),
        [(OrderStatus.PAID, "order_already_paid"), (OrderStatus.EXPIRED, "order_expired")],
    )
    def test_a_paid_or_expired_order_cannot_be_paid(self, status: OrderStatus, reason: str) -> None:
        harness = _Harness(store_with(status))

        with pytest.raises(OrderNotPayableError) as error:
            harness.use_case.execute(ORDER_ID)

        assert error.value.reason == reason
        assert harness.gateway.created == []
        assert harness.names() == ["order.payment_rejected"]
        event = harness.events.events[0]
        assert (event.outcome, event.reason) == (Outcome.DENIED, reason)
        assert event.resource_id == "BC-ABCDEFGHJK"

    def test_an_unknown_order_is_refused_without_echoing_the_identifier(self) -> None:
        harness = _Harness(PaymentStore())

        with pytest.raises(PaymentOrderNotFoundError):
            harness.use_case.execute(ORDER_ID)

        event = harness.events.events[0]
        assert (event.event, event.reason) == ("order.payment_rejected", "order_not_found")
        assert ORDER_ID not in repr(event)

    def test_emits_order_payment_requested_without_sensitive_data(self) -> None:
        harness = _Harness(store_with())

        harness.use_case.execute(ORDER_ID)

        (event,) = harness.events.events
        assert (event.event, event.outcome) == ("order.payment_requested", Outcome.SUCCESS)
        assert (event.resource_type, event.resource_id) == ("order", "BC-ABCDEFGHJK")
        assert event.attributes == {"amount_cents": 4490, "currency": "EUR", "attempt": 1}

    def test_an_unavailable_provider_leaves_no_attempt_and_is_logged_as_an_error(self) -> None:
        harness = _Harness(store_with(), RecordingGateway(unavailable=True))

        with pytest.raises(PaymentUnavailableError):
            harness.use_case.execute(ORDER_ID)

        assert harness.store.attempts == []
        (event,) = harness.events.events
        assert (event.event, event.outcome, event.reason) == (
            "order.payment_unavailable",
            Outcome.ERROR,
            "payment_unavailable",
        )

    def test_the_amount_comes_from_the_stored_order_not_from_the_caller(self) -> None:
        store = store_with()
        store.orders[ORDER_ID] = replace(store.orders[ORDER_ID], total_cents=12345)
        harness = _Harness(store)

        harness.use_case.execute(ORDER_ID)

        assert harness.gateway.created[0][1] == 12345
