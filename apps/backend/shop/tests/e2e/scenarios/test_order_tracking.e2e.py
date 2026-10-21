"""Suivi d'une commande via la passerelle : numéro + email, réponses indiscernables sinon."""

import os
import time
import uuid
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
ORDERS_PATH = "/api/shop/orders"
LOOKUP_PATH = "/api/shop/orders/lookup"
PRODUCT = "trousse-premiers-secours-rando"  # 36,00 EUR, stock confortable
EMAIL = "e2e.suivi@example.org"
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
        "email": EMAIL,
        "shippingAddress": {
            "fullName": "Client E2E",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": PRODUCT, "quantity": 2}],
    }
    response = _post(client, ORDERS_PATH, body, {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})
    assert response.status_code == 201
    return dict(response.json())


class TestOrderTracking:
    def test_a_matching_number_and_email_return_status_lines_and_total(
        self, client: httpx.Client
    ) -> None:
        order = _create_order(client)

        response = _post(client, LOOKUP_PATH, {"orderNumber": order["number"], "email": EMAIL})

        body = response.json()
        assert response.status_code == 200
        assert body["number"] == order["number"]
        assert body["status"] == "pending_payment"
        assert body["total_cents"] == order["total_cents"]
        assert [line["quantity"] for line in body["lines"]] == [2]
        assert EMAIL not in response.text

    def test_the_email_is_compared_without_case(self, client: httpx.Client) -> None:
        order = _create_order(client)

        response = _post(
            client, LOOKUP_PATH, {"orderNumber": order["number"], "email": EMAIL.upper()}
        )

        assert response.status_code == 200

    def test_a_wrong_email_and_an_unknown_number_are_indistinguishable(
        self, client: httpx.Client
    ) -> None:
        order = _create_order(client)

        wrong_email = _post(
            client, LOOKUP_PATH, {"orderNumber": order["number"], "email": "intrus@example.org"}
        )
        unknown = _post(client, LOOKUP_PATH, {"orderNumber": "BC-ZZZZZZZZZZ", "email": EMAIL})

        assert wrong_email.status_code == unknown.status_code == 404
        assert wrong_email.content == unknown.content
        assert EMAIL not in wrong_email.text

    def test_an_invalid_number_is_refused_without_reflecting_it(self, client: httpx.Client) -> None:
        response = _post(client, LOOKUP_PATH, {"orderNumber": "zz-evil-zz", "email": EMAIL})

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text
