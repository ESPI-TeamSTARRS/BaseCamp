"""Devis du panier via la passerelle : le serveur seul decide des prix, de la livraison et du stock."""

import os
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
QUOTE_PATH = "/api/shop/cart/quote"
TENT = "tente-bivouac-ultralight-2p"  # 329,00 EUR
POT = "popote-titane-900ml"  # 39,00 EUR
LOW_STOCK = "sac-a-dos-ultralight-38l"  # 4 en stock
SOLD_OUT = "sac-de-couchage-synthetique-0"  # 0 en stock


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def _quote(client: httpx.Client, *items: tuple[str, int]) -> httpx.Response:
    payload = {"lines": [{"productId": pid, "quantity": qty} for pid, qty in items]}
    return client.post(QUOTE_PATH, json=payload)


class TestQuoteAmounts:
    def test_quote_is_computed_from_database_prices_with_free_shipping(
        self, client: httpx.Client
    ) -> None:
        body = _quote(client, (TENT, 1), (POT, 2)).json()

        assert [line["line_total_cents"] for line in body["lines"]] == [32900, 7800]
        assert body["subtotal_cents"] == 40700
        assert body["shipping_cents"] == 0
        assert body["total_cents"] == 40700
        assert body["has_issues"] is False

    def test_shipping_is_590_below_80_euros(self, client: httpx.Client) -> None:
        body = _quote(client, (POT, 1)).json()

        assert body["subtotal_cents"] == 3900
        assert body["shipping_cents"] == 590
        assert body["total_cents"] == 4490
        assert body["free_shipping_threshold_cents"] == 8000
        assert body["amount_remaining_for_free_shipping_cents"] == 4100


class TestQuoteValidation:
    def test_a_client_price_is_refused(self, client: httpx.Client) -> None:
        payload = {"lines": [{"productId": TENT, "quantity": 1, "price": 1}]}

        response = client.post(QUOTE_PATH, json=payload)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "lines",
        [
            [],
            [{"productId": TENT, "quantity": 11}],
            [{"productId": TENT, "quantity": 0}],
            [{"productId": f"p{i}", "quantity": 1} for i in range(51)],
            [{"productId": "zz-evil-zz", "quantity": 1}],
        ],
    )
    def test_invalid_carts_return_422_without_reflecting_the_input(
        self, client: httpx.Client, lines: list[dict[str, Any]]
    ) -> None:
        response = client.post(QUOTE_PATH, json={"lines": lines})

        assert response.status_code == 422
        assert "zz-evil-zz" not in response.text


class TestQuoteStock:
    def test_quantity_above_stock_is_flagged_with_the_available_quantity(
        self, client: httpx.Client
    ) -> None:
        body = _quote(client, (LOW_STOCK, 5)).json()

        assert body["lines"][0]["status"] == "insufficient_stock"
        assert body["lines"][0]["available_quantity"] == 4
        assert body["has_issues"] is True

    def test_sold_out_product_is_flagged_with_zero_available(self, client: httpx.Client) -> None:
        line = _quote(client, (SOLD_OUT, 1)).json()["lines"][0]

        assert line["status"] == "insufficient_stock"
        assert line["available_quantity"] == 0
