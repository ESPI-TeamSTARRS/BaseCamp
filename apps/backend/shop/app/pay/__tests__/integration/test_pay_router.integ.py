from typing import Any

from httpx import ASGITransport, AsyncClient

from app.cart.__tests__.fake_cart_product_reader import FakeCartProductReader, default_catalog
from app.cart.application.quote_cart import QuoteCartUseCase
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app
from app.pay.application.start_payment import StartPaymentUseCase
from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef
from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError
from app.pay.domain.interfaces.payment_gateway import PaymentGateway

KEY = {"Idempotency-Key": "key-00000001"}
BODY = {"order_reference": "CMD-1", "lines": [{"productId": "popote", "quantity": 1}]}


class FakeGateway(PaymentGateway):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.amounts: list[int] = []

    def create_intent(
        self, order_reference: str, amount_cents: int, currency: str, idempotency_key: str
    ) -> PaymentIntentRef:
        if self.error:
            raise self.error
        self.amounts.append(amount_cents)
        return PaymentIntentRef("intent-1", "requires_confirmation", amount_cents, currency)


async def _post(
    gateway: FakeGateway, body: Any = BODY, headers: dict[str, str] | None = None
) -> Any:
    application = create_app()
    events = InMemoryBusinessEventLogger()
    application.state.start_payment_use_case = StartPaymentUseCase(
        QuoteCartUseCase(FakeCartProductReader(default_catalog()), events), gateway, events
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post("/pay", json=body, headers=KEY if headers is None else headers)


class TestPayRouter:
    async def test_creates_the_intent_for_the_server_side_total(self) -> None:
        gateway = FakeGateway()

        response = await _post(gateway)

        assert response.status_code == 201
        assert response.json() == {
            "payment_intent_id": "intent-1",
            "status": "requires_confirmation",
            "amount_cents": 4490,
            "currency": "EUR",
        }
        assert gateway.amounts == [4490]

    async def test_a_client_amount_is_refused(self) -> None:
        response = await _post(FakeGateway(), {**BODY, "amount": 1})

        assert response.status_code == 422

    async def test_the_idempotency_key_is_required(self) -> None:
        response = await _post(FakeGateway(), headers={})

        assert response.status_code == 422

    async def test_an_invalid_cart_is_a_422(self) -> None:
        body = {"order_reference": "CMD-1", "lines": [{"productId": "rare", "quantity": 5}]}

        response = await _post(FakeGateway(), body)

        assert response.status_code == 422

    async def test_payment_down_gives_a_clean_503_with_retry_after(self) -> None:
        response = await _post(FakeGateway(PaymentUnavailableError()))

        assert response.status_code == 503
        assert response.json() == {"detail": "Paiement indisponible, reessayez plus tard."}
        assert response.headers["Retry-After"] == "5"

    async def test_business_refusals_are_relayed_without_details(self) -> None:
        conflict = await _post(FakeGateway(PaymentRejectedError(conflict=True)))
        refused = await _post(FakeGateway(PaymentRejectedError(conflict=False)))

        assert (conflict.status_code, refused.status_code) == (409, 422)
        assert conflict.json() == {"detail": "Paiement refuse."}
