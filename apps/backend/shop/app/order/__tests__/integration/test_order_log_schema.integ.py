"""Les lignes JSON reellement ecrites par POST /orders respectent le schema commun de logs."""

import io
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.order.__tests__.fake_order_unit_of_work import (
    FakeOrderUnitOfWork,
    FakePseudonymizer,
    InMemoryStore,
    default_stock,
)
from app.order.application.place_order import PlaceOrderUseCase

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
EMAIL = "camille.martin@example.org"


def _body(country: str = "FR", product: str = "popote", quantity: int = 1) -> dict[str, Any]:
    return {
        "email": EMAIL,
        "shippingAddress": {
            "fullName": "Camille Martin",
            "line1": "12 rue des Alpes",
            "postalCode": "38000",
            "city": "Grenoble",
            "country": country,
        },
        "lines": [{"productId": product, "quantity": quantity}],
    }


async def _post(
    stream: io.StringIO, store: InMemoryStore, key: str, payload: dict[str, Any]
) -> int:
    application = create_app()
    application.state.place_order_use_case = PlaceOrderUseCase(
        lambda: FakeOrderUnitOfWork(store),
        StructlogBusinessEventLogger("basecamp-shop", stream),
        FakePseudonymizer(),
    )
    headers = {"Idempotency-Key": key, "X-Correlation-ID": CORRELATION_ID}
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        return (await client.post("/orders", json=payload, headers=headers)).status_code


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class TestOrderLogsFollowTheCommonSchema:
    async def test_every_emitted_line_is_valid_and_carries_the_request_correlation_id(self) -> None:
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        stream, store = io.StringIO(), InMemoryStore(stock=default_stock())

        await _post(
            stream, store, "cle-schema-0001", _body()
        )  # 201 : stock.reserved + order.created
        await _post(stream, store, "cle-schema-0001", _body())  # 200 : order.replayed
        await _post(stream, store, "cle-schema-0002", _body(country="US"))  # 422 : order.rejected
        await _post(stream, store, "cle-schema-0003", _body(product="rare", quantity=5))  # 409

        records = _lines(stream)
        assert [r["event"] for r in records] == [
            "stock.reserved",
            "order.created",
            "order.replayed",
            "order.rejected",
            "stock.insufficient",
        ]
        for record in records:
            validator.validate(record)
            assert record["correlation_id"] == CORRELATION_ID
            assert record["service"] == "basecamp-shop"

    async def test_the_raw_output_never_contains_the_email_the_address_or_the_key(self) -> None:
        stream, store = io.StringIO(), InMemoryStore(stock=default_stock())

        await _post(stream, store, "cle-secrete-0001", _body())

        raw = stream.getvalue()
        assert EMAIL not in raw
        assert "camille" not in raw.lower()
        assert "rue des Alpes" not in raw
        assert "cle-secrete-0001" not in raw
        assert "email_hash" in raw
