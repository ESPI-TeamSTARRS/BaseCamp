"""Creation de commande via la passerelle : prix figes, stock reserve, rejeu idempotent."""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
ORDERS_PATH = "/api/shop/orders"
QUOTE_PATH = "/api/shop/cart/quote"
FILTER = "filtre-a-eau-portable"  # 34,00 EUR, gros stock
SOLD_OUT = "sac-de-couchage-synthetique-0"  # 0 en stock


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15.0)


def _body(product_id: str = FILTER, quantity: int = 1, country: str = "FR") -> dict[str, Any]:
    return {
        "email": "e2e.client@example.org",
        "shippingAddress": {
            "fullName": "Client E2E",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": country,
        },
        "lines": [{"productId": product_id, "quantity": quantity}],
    }


RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8


def _post(
    client: httpx.Client, body: dict[str, Any], headers: dict[str, str] | None = None
) -> httpx.Response:
    """POST /orders ; sur 429 de la passerelle on patiente puis on rejoue (la cle rend le rejeu sur)."""
    response = client.post(ORDERS_PATH, json=body, headers=headers)
    for _ in range(RATE_LIMIT_ATTEMPTS):
        if response.status_code != 429:
            break
        time.sleep(RATE_LIMIT_PAUSE_SECONDS)
        response = client.post(ORDERS_PATH, json=body, headers=headers)
    return response


def _key() -> str:
    return f"e2e-{uuid.uuid4().hex}"


def _available(client: httpx.Client, product_id: str) -> int:
    quote = client.post(QUOTE_PATH, json={"lines": [{"productId": product_id, "quantity": 1}]})
    return int(quote.json()["lines"][0]["available_quantity"])


class TestPlaceOrder:
    def test_creates_a_pending_order_reserves_stock_and_freezes_prices(
        self, client: httpx.Client
    ) -> None:
        before = _available(client, FILTER)

        response = _post(client, _body(quantity=2), {"Idempotency-Key": _key()})

        body = response.json()
        assert response.status_code == 201
        assert body["status"] == "pending_payment"
        assert body["number"].startswith("BC-")
        assert body["lines"][0]["unit_price_cents"] == 3400
        assert (body["subtotal_cents"], body["shipping_cents"], body["total_cents"]) == (
            6800,
            590,
            7390,
        )
        assert _available(client, FILTER) == before - 2

    def test_the_same_key_replayed_returns_the_same_order_without_a_second_reservation(
        self, client: httpx.Client
    ) -> None:
        headers = {"Idempotency-Key": _key()}
        first = _post(client, _body(), headers)
        after_first = _available(client, FILTER)

        second = _post(client, _body(), headers)

        assert (first.status_code, second.status_code) == (201, 200)
        assert second.json()["id"] == first.json()["id"]
        assert _available(client, FILTER) == after_first

    def test_the_same_key_sent_in_parallel_creates_a_single_order(
        self, client: httpx.Client
    ) -> None:
        headers = {"Idempotency-Key": _key()}

        with ThreadPoolExecutor(max_workers=3) as pool:
            responses = list(pool.map(lambda _: _post(client, _body(), headers), range(3)))

        assert {r.status_code for r in responses} <= {200, 201}
        assert sum(r.status_code == 201 for r in responses) == 1
        assert len({r.json()["id"] for r in responses}) == 1

    def test_a_sold_out_product_returns_409(self, client: httpx.Client) -> None:
        response = _post(client, _body(product_id=SOLD_OUT), {"Idempotency-Key": _key()})

        assert response.status_code == 409

    def test_a_country_outside_the_list_returns_422(self, client: httpx.Client) -> None:
        response = _post(client, _body(country="US"), {"Idempotency-Key": _key()})

        assert response.status_code == 422
        assert response.json() == {"detail": "Pays de livraison non pris en charge."}

    def test_the_idempotency_key_is_required(self, client: httpx.Client) -> None:
        assert _post(client, _body()).status_code == 422
