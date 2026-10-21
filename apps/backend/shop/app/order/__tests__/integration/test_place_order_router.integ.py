from typing import Any

from httpx import ASGITransport, AsyncClient

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app
from app.order.__tests__.fake_order_unit_of_work import (
    FakeOrderUnitOfWork,
    FakePseudonymizer,
    InMemoryStore,
    default_stock,
)
from app.order.application.place_order import PlaceOrderUseCase

KEY = "cle-router-0001"


def _body(
    country: str = "FR", items: tuple[tuple[str, int], ...] = (("popote", 1),)
) -> dict[str, Any]:
    return {
        "email": "camille.martin@example.org",
        "shippingAddress": {
            "fullName": "Camille Martin",
            "line1": "12 rue des Alpes",
            "postalCode": "38000",
            "city": "Grenoble",
            "country": country,
        },
        "lines": [{"productId": pid, "quantity": qty} for pid, qty in items],
    }


class _Client:
    def __init__(self) -> None:
        self.store = InMemoryStore(stock=default_stock())
        self.events = InMemoryBusinessEventLogger()
        self.application = create_app()
        self.application.state.place_order_use_case = PlaceOrderUseCase(
            lambda: FakeOrderUnitOfWork(self.store), self.events, FakePseudonymizer()
        )

    async def post(self, payload: Any, headers: dict[str, str] | None = None) -> Any:
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            return await client.post("/orders", json=payload, headers=headers)


def _headers(key: str | None = KEY, **extra: str) -> dict[str, str]:
    headers = dict(extra)
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


class TestPlaceOrderRouter:
    async def test_creates_a_pending_order_with_frozen_prices(self) -> None:
        response = await _Client().post(_body(), _headers())

        body = response.json()
        assert response.status_code == 201
        assert body["status"] == "pending_payment"
        assert body["number"].startswith("BC-")
        assert body["lines"] == [
            {
                "product_id": "popote",
                "name": "Popote",
                "unit_price_cents": 3900,
                "quantity": 1,
                "line_total_cents": 3900,
            }
        ]
        assert (body["subtotal_cents"], body["shipping_cents"], body["total_cents"]) == (
            3900,
            590,
            4490,
        )
        assert body["shipping_address"]["country"] == "FR"

    async def test_replaying_the_key_returns_200_and_the_same_order(self) -> None:
        client = _Client()
        first = await client.post(_body(), _headers())
        second = await client.post(_body(), _headers())

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert len(client.store.orders) == 1

    async def test_the_key_reused_with_another_content_returns_422(self) -> None:
        client = _Client()
        await client.post(_body(), _headers())

        response = await client.post(_body(items=(("popote", 3),)), _headers())

        assert response.status_code == 422
        assert (
            response.json()["detail"]
            == "Cette cle d'idempotence est deja utilisee pour une autre commande."
        )

    async def test_insufficient_stock_returns_409_and_reserves_nothing(self) -> None:
        client = _Client()

        response = await client.post(_body(items=(("tente", 1), ("rare", 3))), _headers())

        assert response.status_code == 409
        assert response.json() == {"detail": "Stock insuffisant pour un ou plusieurs articles."}
        assert client.store.stock["tente"].stock == 24
        assert client.store.reservations == []

    async def test_country_outside_the_list_returns_422_with_a_fixed_message(self) -> None:
        response = await _Client().post(_body(country="US"), _headers())

        assert response.status_code == 422
        assert response.json() == {"detail": "Pays de livraison non pris en charge."}

    async def test_the_idempotency_key_header_is_required(self) -> None:
        response = await _Client().post(_body(), _headers(key=None))

        assert response.status_code == 422

    async def test_a_price_sent_by_the_client_is_refused(self) -> None:
        payload = _body()
        payload["lines"][0]["price"] = 1

        response = await _Client().post(payload, _headers())

        assert response.status_code == 422

    async def test_unknown_product_returns_422_without_echoing_the_id(self) -> None:
        response = await _Client().post(_body(items=(("zz-evil-zz", 1),)), _headers())

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text

    async def test_invalid_input_is_never_reflected(self) -> None:
        payload = _body()
        payload["email"] = "zz-evil-zz"

        response = await _Client().post(payload, _headers())

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text

    async def test_a_valid_correlation_id_is_echoed_by_the_middleware(self) -> None:
        response = await _Client().post(
            _body(), _headers(**{"X-Correlation-ID": "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"})
        )

        assert response.headers["X-Correlation-ID"] == "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"

    async def test_an_unsafe_correlation_id_is_replaced(self) -> None:
        response = await _Client().post(_body(), _headers(**{"X-Correlation-ID": "a b	c"}))

        assert response.headers["X-Correlation-ID"] != "a b	c"
        assert len(response.headers["X-Correlation-ID"]) >= 16
