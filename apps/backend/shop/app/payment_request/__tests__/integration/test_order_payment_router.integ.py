import io
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.order.domain.enums.order_status import OrderStatus
from app.payment_request.__tests__.fakes import (
    ORDER_ID,
    OTHER_ORDER_ID,
    FakePaymentUnitOfWork,
    PaymentStore,
    RecordingGateway,
    store_with,
)
from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class _Client:
    def __init__(
        self,
        store: PaymentStore | None = None,
        gateway: RecordingGateway | None = None,
        events: Any = None,
    ) -> None:
        self.store = store or store_with()
        self.gateway = gateway or RecordingGateway()
        self.events = events or InMemoryBusinessEventLogger()
        factory = lambda: FakePaymentUnitOfWork(self.store)  # noqa: E731
        self.application = create_app()
        self.application.state.request_order_payment_use_case = RequestOrderPaymentUseCase(
            factory, self.gateway, self.events
        )
        self.application.state.confirm_order_payment_use_case = ConfirmOrderPaymentUseCase(
            factory, self.gateway, self.events
        )

    async def post(self, path: str, payload: Any = None) -> Any:
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            headers = {"X-Correlation-ID": CORRELATION_ID}
            return await client.post(path, json=payload, headers=headers)


def _pay(order_id: str = ORDER_ID) -> str:
    return f"/orders/{order_id}/pay"


def _confirm(order_id: str = ORDER_ID) -> str:
    return f"/orders/{order_id}/pay/confirm"


class TestPayOrderRoute:
    async def test_returns_what_the_front_needs_to_confirm(self) -> None:
        response = await _Client().post(_pay())

        assert response.status_code == 201
        assert response.json() == {
            "payment_intent_id": "pi-1",
            "status": "requires_confirmation",
            "amount_cents": 4490,
            "currency": "EUR",
            "order_number": "BC-ABCDEFGHJK",
            "payment_methods": ["pm_test_success", "pm_test_declined"],
        }

    async def test_asking_again_returns_the_same_intent_with_200(self) -> None:
        client = _Client()
        first = await client.post(_pay())

        second = await client.post(_pay())

        assert second.status_code == 200
        assert second.json()["payment_intent_id"] == first.json()["payment_intent_id"]

    async def test_a_paid_or_expired_order_returns_409_with_a_fixed_message(self) -> None:
        paid = await _Client(store_with(OrderStatus.PAID)).post(_pay())
        expired = await _Client(store_with(OrderStatus.EXPIRED)).post(_pay())

        assert (paid.status_code, paid.json()) == (409, {"detail": "Commande deja payee."})
        assert (expired.status_code, expired.json()) == (409, {"detail": "Commande expiree."})

    async def test_an_unknown_order_returns_404_without_echoing_the_identifier(self) -> None:
        response = await _Client().post(_pay(OTHER_ORDER_ID))

        assert response.status_code == 404
        assert OTHER_ORDER_ID not in response.text

    async def test_a_malformed_identifier_returns_a_sanitised_422(self) -> None:
        response = await _Client().post("/orders/zz-evil-zz/pay")

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text

    async def test_an_unavailable_provider_returns_503_with_retry_after(self) -> None:
        response = await _Client(gateway=RecordingGateway(unavailable=True)).post(_pay())

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "5"


class TestConfirmOrderPaymentRoute:
    async def test_a_successful_payment_marks_the_order_paid(self) -> None:
        client = _Client()
        await client.post(_pay())

        response = await client.post(_confirm(), {"payment_method": "pm_test_success"})

        assert response.status_code == 200
        assert response.json() == {
            "order_number": "BC-ABCDEFGHJK",
            "order_status": "paid",
            "payment_status": "succeeded",
        }
        assert client.store.orders[ORDER_ID].status is OrderStatus.PAID

    async def test_a_declined_payment_is_a_200_business_result_and_the_order_stays_pending(
        self,
    ) -> None:
        client = _Client()
        await client.post(_pay())

        response = await client.post(_confirm(), {"payment_method": "pm_test_declined"})

        assert response.status_code == 200
        assert response.json()["order_status"] == "pending_payment"
        assert response.json()["payment_status"] == "failed"

    async def test_paying_twice_returns_409(self) -> None:
        client = _Client()
        await client.post(_pay())
        await client.post(_confirm(), {"payment_method": "pm_test_success"})

        again = await client.post(_confirm(), {"payment_method": "pm_test_success"})

        assert again.status_code == 409

    async def test_a_card_number_is_refused_and_never_reflected(self) -> None:
        client = _Client()
        await client.post(_pay())

        response = await client.post(_confirm(), {"payment_method": "4242424242424242"})

        assert response.status_code == 422
        assert "4242" not in response.text

    async def test_extra_fields_are_refused(self) -> None:
        client = _Client()
        await client.post(_pay())

        response = await client.post(_confirm(), {"payment_method": "pm_test_success", "amount": 1})

        assert response.status_code == 422

    async def test_confirming_without_a_pending_intent_returns_409(self) -> None:
        response = await _Client().post(_confirm(), {"payment_method": "pm_test_success"})

        assert response.status_code == 409

    async def test_payment_received_after_expiry_is_a_409_and_is_logged(self) -> None:
        client = _Client()
        await client.post(_pay())
        client.store.orders[ORDER_ID] = client.store.orders[ORDER_ID].__class__(
            ORDER_ID, "BC-ABCDEFGHJK", OrderStatus.EXPIRED, 4490
        )

        response = await client.post(_confirm(), {"payment_method": "pm_test_success"})

        assert response.status_code == 409
        assert response.json() == {"detail": "Commande expiree."}
        assert client.events.events[-1].reason == "order_expired"


class TestOrderPaymentLogsFollowTheCommonSchema:
    async def test_every_emitted_line_is_valid_and_correlated(self) -> None:
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        stream = io.StringIO()
        client = _Client(events=StructlogBusinessEventLogger("basecamp-shop", stream))

        await client.post(_pay())  # order.payment_requested
        await client.post(
            _confirm(), {"payment_method": "pm_test_declined"}
        )  # order.payment_failed
        await client.post(_pay())  # order.payment_requested (tentative 2)
        await client.post(_confirm(), {"payment_method": "pm_test_success"})  # order.paid
        await client.post(_pay())  # order.payment_rejected (déjà payée)
        await client.post(_pay(OTHER_ORDER_ID))  # order.payment_rejected (introuvable)

        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert [r["event"] for r in records] == [
            "order.payment_requested",
            "order.payment_failed",
            "order.payment_requested",
            "order.paid",
            "order.payment_rejected",
            "order.payment_rejected",
        ]
        for record in records:
            validator.validate(record)
            assert record["correlation_id"] == CORRELATION_ID
        raw = stream.getvalue()
        assert ORDER_ID not in raw
        assert "Authorization" not in raw
