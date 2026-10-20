import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.cart.__tests__.fake_cart_product_reader import FakeCartProductReader, default_catalog
from app.cart.application.quote_cart import QuoteCartUseCase
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app


async def _post(payload: Any) -> tuple[int, Any]:
    application = create_app()
    application.state.quote_cart_use_case = QuoteCartUseCase(
        FakeCartProductReader(default_catalog()), InMemoryBusinessEventLogger()
    )
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        response = await client.post("/cart/quote", json=payload)
    return response.status_code, response.json()


def _lines(*items: tuple[str, int]) -> dict[str, Any]:
    return {"lines": [{"productId": pid, "quantity": qty} for pid, qty in items]}


class TestCartQuoteRouter:
    async def test_returns_lines_subtotal_shipping_and_total(self) -> None:
        status_code, body = await _post(_lines(("popote", 1)))

        assert status_code == 200
        assert body["subtotal_cents"] == 3900
        assert body["shipping_cents"] == 590
        assert body["total_cents"] == 4490
        assert body["free_shipping_threshold_cents"] == 8000
        assert body["amount_remaining_for_free_shipping_cents"] == 4100
        assert body["has_issues"] is False
        line = body["lines"][0]
        assert line == {
            "product_id": "popote",
            "name": "Popote",
            "unit_price_cents": 3900,
            "quantity": 1,
            "line_total_cents": 3900,
            "status": "ok",
            "available_quantity": 56,
        }

    async def test_signals_insufficient_stock_with_the_available_quantity(self) -> None:
        _, body = await _post(_lines(("rare", 5)))

        assert body["lines"][0]["status"] == "insufficient_stock"
        assert body["lines"][0]["available_quantity"] == 2
        assert body["has_issues"] is True

    async def test_a_price_sent_by_the_client_is_refused_and_never_used(self) -> None:
        payload = {"lines": [{"productId": "tente", "quantity": 1, "price": 1}]}

        status_code, body = await _post(payload)

        assert status_code == 422
        assert body["detail"] == "Requete invalide."

    async def test_unexpected_top_level_fields_are_refused(self) -> None:
        status_code, _ = await _post({**_lines(("tente", 1)), "discount": 50})

        assert status_code == 422

    async def test_extra_field_names_are_not_reflected(self) -> None:
        payload = {"lines": [{"productId": "tente", "quantity": 1, "zz-evil-zz": 1}]}

        _, body = await _post(payload)

        assert "zz-evil-zz" not in str(body)

    async def test_rejects_quantity_above_ten_and_below_one(self) -> None:
        assert (await _post(_lines(("tente", 11))))[0] == 422
        assert (await _post(_lines(("tente", 0))))[0] == 422

    async def test_rejects_an_empty_cart_and_more_than_fifty_lines(self) -> None:
        assert (await _post({"lines": []}))[0] == 422
        too_many = _lines(*[(f"p{i}", 1) for i in range(51)])
        assert (await _post(too_many))[0] == 422

    async def test_unknown_product_returns_422_without_echoing_the_id(self) -> None:
        status_code, body = await _post(_lines(("zz-evil-zz", 1)))

        assert status_code == 422
        assert "zz-evil-zz" not in str(body)

    async def test_wrong_types_return_422_without_echoing_the_input(self) -> None:
        status_code, body = await _post(
            {"lines": [{"productId": "tente", "quantity": "zz-evil-zz"}]}
        )

        assert status_code == 422
        assert "zz-evil-zz" not in str(body)


class TestCartQuoteLogging:
    async def test_the_quote_writes_one_correlated_json_line_on_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        application = create_app()
        application.state.quote_cart_use_case = QuoteCartUseCase(
            FakeCartProductReader(default_catalog()), application.state.events
        )
        correlation_id = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.post(
                "/cart/quote",
                json=_lines(("tente", 1)),
                headers={"X-Correlation-ID": correlation_id},
            )

        (line,) = capsys.readouterr().out.strip().splitlines()
        record = json.loads(line)
        assert response.headers["X-Correlation-ID"] == correlation_id
        assert (record["event"], record["outcome"], record["service"]) == (
            "cart.quoted",
            "success",
            "basecamp-shop",
        )
        assert record["correlation_id"] == correlation_id
