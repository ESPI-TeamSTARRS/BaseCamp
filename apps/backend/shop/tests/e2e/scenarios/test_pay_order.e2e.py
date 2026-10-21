"""Paiement d'une commande via la passerelle : intention, confirmation de test, refus, nouvel essai."""

import os
import time
import uuid
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
ORDERS_PATH = "/api/shop/orders"
PRODUCT = "boussole-orientation-pro"  # 29,00 EUR, gros stock, non utilisé par les autres scénarios
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15.0)


def _post(client: httpx.Client, path: str, body: Any, headers: dict[str, str] | None = None) -> Any:
    """POST ; sur 429 de la passerelle on patiente puis on rejoue (les routes sont idempotentes)."""
    response = client.post(path, json=body, headers=headers)
    for _ in range(RATE_LIMIT_ATTEMPTS):
        if response.status_code != 429:
            break
        time.sleep(RATE_LIMIT_PAUSE_SECONDS)
        response = client.post(path, json=body, headers=headers)
    return response


def _create_order(client: httpx.Client) -> dict[str, Any]:
    body = {
        "email": "e2e.paiement@example.org",
        "shippingAddress": {
            "fullName": "Client E2E",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": PRODUCT, "quantity": 3}],
    }
    response = _post(client, ORDERS_PATH, body, {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})
    assert response.status_code == 201
    return dict(response.json())


class TestPayOrder:
    def test_pays_an_order_with_a_test_method_and_cannot_pay_it_twice(
        self, client: httpx.Client
    ) -> None:
        order = _create_order(client)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"

        intent = _post(client, pay, None)
        paid = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_success"})
        again = _post(client, pay, None)

        assert intent.status_code == 201
        assert intent.json()["amount_cents"] == order["total_cents"]
        assert intent.json()["currency"] == "EUR"
        assert paid.status_code == 200
        assert paid.json()["order_status"] == "paid"
        assert paid.json()["payment_status"] == "succeeded"
        assert again.status_code == 409

    def test_a_declined_payment_can_be_retried_until_it_succeeds(
        self, client: httpx.Client
    ) -> None:
        order = _create_order(client)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"
        _post(client, pay, None)

        declined = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_declined"})
        retry = _post(client, pay, None)
        paid = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_success"})

        assert declined.json()["order_status"] == "pending_payment"
        assert declined.json()["payment_status"] == "failed"
        assert retry.status_code == 201
        assert paid.json()["order_status"] == "paid"

    def test_a_card_number_is_refused(self, client: httpx.Client) -> None:
        order = _create_order(client)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"
        _post(client, pay, None)

        response = _post(client, f"{pay}/confirm", {"payment_method": "4242424242424242"})

        assert response.status_code == 422
        assert "4242" not in response.text

    def test_an_unknown_order_returns_404(self, client: httpx.Client) -> None:
        response = _post(client, f"{ORDERS_PATH}/{uuid.uuid4()}/pay", None)

        assert response.status_code == 404
