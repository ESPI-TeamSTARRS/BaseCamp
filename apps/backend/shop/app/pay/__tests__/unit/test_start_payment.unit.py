import pytest

from app.cart.__tests__.fake_cart_product_reader import FakeCartProductReader, default_catalog
from app.cart.application.invalid_cart_error import InvalidCartError
from app.cart.application.quote_cart import QuoteCartUseCase
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.pay.application.start_payment import StartPaymentUseCase
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway


class RecordingGateway(PaymentGateway):
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, int, str, str]] = []
        self._error = error

    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        if self._error:
            raise self._error
        self.calls.append((order_reference, amount_cents, currency, idempotency_key))
        return PaymentIntentRef("intent-1", "requires_confirmation", amount_cents, currency)


EVENTS = InMemoryBusinessEventLogger()


def _use_case(
    gateway: PaymentGateway, events: InMemoryBusinessEventLogger = EVENTS
) -> StartPaymentUseCase:
    quote = QuoteCartUseCase(FakeCartProductReader(default_catalog()), events)
    return StartPaymentUseCase(quote, gateway, events)


class TestStartPayment:
    def test_the_amount_sent_to_payment_is_the_server_side_quote_total(self) -> None:
        gateway = RecordingGateway()

        intent = _use_case(gateway).execute("CMD-1", [("popote", 1)], "key-00000001")

        # 39,00 EUR + 5,90 EUR de livraison sous le seuil de gratuité
        assert gateway.calls == [("CMD-1", 4490, "EUR", "key-00000001")]
        assert intent.id == "intent-1"

    def test_a_cart_with_insufficient_stock_never_reaches_payment(self) -> None:
        gateway = RecordingGateway()

        with pytest.raises(InvalidCartError):
            _use_case(gateway).execute("CMD-1", [("rare", 5)], "key-00000001")

        assert gateway.calls == []

    def test_an_unknown_product_never_reaches_payment(self) -> None:
        gateway = RecordingGateway()

        with pytest.raises(InvalidCartError):
            _use_case(gateway).execute("CMD-1", [("fantome", 1)], "key-00000001")

        assert gateway.calls == []

    def test_a_payment_outage_is_propagated(self) -> None:
        with pytest.raises(PaymentUnavailableError):
            _use_case(RecordingGateway(PaymentUnavailableError())).execute(
                "CMD-1", [("popote", 1)], "key-00000001"
            )


class TestStartPaymentEvents:
    def test_success_emits_payment_started_with_the_intent_and_no_order_reference(self) -> None:
        events = InMemoryBusinessEventLogger()

        _use_case(RecordingGateway(), events).execute("CMD-1", [("popote", 1)], "key-00000001")

        started = events.events[-1]
        assert (started.event, started.outcome.value) == ("pay.payment_started", "success")
        assert (started.resource_type, started.resource_id) == ("payment_intent", "intent-1")
        assert started.attributes == {"amount_cents": 4490, "currency": "EUR"}
        assert "CMD-1" not in str(started) and "key-00000001" not in str(started)

    def test_an_outage_emits_an_error_event_with_a_stable_code(self) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(PaymentUnavailableError):
            _use_case(RecordingGateway(PaymentUnavailableError()), events).execute(
                "CMD-1", [("popote", 1)], "key-00000001"
            )

        last = events.events[-1]
        assert (last.event, last.outcome.value, last.reason) == (
            "pay.payment_unavailable",
            "error",
            "payment_unavailable",
        )

    def test_refusals_emit_denied_events(self) -> None:
        events = InMemoryBusinessEventLogger()
        for error, expected in (
            (PaymentRejectedError(True), "payment_conflict"),
            (PaymentRejectedError(False), "payment_refused"),
        ):
            with pytest.raises(PaymentRejectedError):
                _use_case(RecordingGateway(error), events).execute(
                    "CMD-1", [("popote", 1)], "key-00000001"
                )
            assert events.events[-1].reason == expected

        with pytest.raises(InvalidCartError):
            _use_case(RecordingGateway(), events).execute("CMD-1", [("rare", 5)], "key-00000001")
        assert events.events[-1].reason == "insufficient_stock"
