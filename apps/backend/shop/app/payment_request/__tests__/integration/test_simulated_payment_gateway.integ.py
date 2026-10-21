from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.order.infrastructure.models.order_base import OrderBase
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.payment_request.infrastructure.gateways.simulated_payment_gateway import (
    SimulatedPaymentGateway,
)


@pytest.fixture
def gateway() -> Iterator[SimulatedPaymentGateway]:
    engine: Engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    OrderBase.metadata.create_all(engine)
    yield SimulatedPaymentGateway(engine)
    engine.dispose()


class TestSimulatedPaymentGateway:
    def test_creates_an_intent_awaiting_confirmation(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        intent = gateway.create_intent("BC-1", 4490, "EUR", "order-BC-1-1")

        assert (intent.status, intent.amount_cents, intent.currency) == (
            "requires_confirmation",
            4490,
            "EUR",
        )
        assert gateway.get_intent(intent.id) == intent

    def test_the_same_key_returns_the_same_intent(self, gateway: SimulatedPaymentGateway) -> None:
        first = gateway.create_intent("BC-1", 4490, "EUR", "order-BC-1-1")

        assert gateway.create_intent("BC-1", 4490, "EUR", "order-BC-1-1") == first

    def test_the_same_key_for_another_request_is_refused(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        gateway.create_intent("BC-1", 4490, "EUR", "order-BC-1-1")

        with pytest.raises(PaymentRejectedError) as error:
            gateway.create_intent("BC-1", 9999, "EUR", "order-BC-1-1")

        assert error.value.conflict is False

    def test_another_key_for_a_known_reference_is_a_conflict(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        gateway.create_intent("BC-1", 4490, "EUR", "order-BC-1-1")

        with pytest.raises(PaymentRejectedError) as error:
            gateway.create_intent("BC-1", 4490, "EUR", "autre-cle-0001")

        assert error.value.conflict is True

    def test_a_success_method_succeeds_and_a_declined_method_fails(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        ok = gateway.create_intent("BC-1", 100, "EUR", "k-00000001")
        ko = gateway.create_intent("BC-2", 100, "EUR", "k-00000002")

        assert gateway.confirm_intent(ok.id, "pm_test_success", "c-00000001").status == "succeeded"
        assert gateway.confirm_intent(ko.id, "pm_test_declined", "c-00000002").status == "failed"

    def test_a_terminal_intent_is_not_confirmed_again(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        intent = gateway.create_intent("BC-1", 100, "EUR", "k-00000001")
        gateway.confirm_intent(intent.id, "pm_test_declined", "c-00000001")

        again = gateway.confirm_intent(intent.id, "pm_test_success", "c-00000002")

        assert again.status == "failed"

    def test_unknown_intents_and_methods_are_refused(
        self, gateway: SimulatedPaymentGateway
    ) -> None:
        intent = gateway.create_intent("BC-1", 100, "EUR", "k-00000001")

        with pytest.raises(PaymentRejectedError):
            gateway.get_intent("inconnue")
        with pytest.raises(PaymentRejectedError):
            gateway.confirm_intent(intent.id, "4242424242424242", "c-00000001")
