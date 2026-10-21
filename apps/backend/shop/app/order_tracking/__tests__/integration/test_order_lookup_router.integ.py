import io
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order_tracking.__tests__.fakes import (
    EMAIL,
    NUMBER,
    FakeTrackedOrderReader,
    tracked_order,
)
from app.order_tracking.application.lookup_order import LookupOrderUseCase

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class _Client:
    def __init__(self, stream: io.StringIO | None = None, status: str = "pending_payment") -> None:
        self.stream = stream or io.StringIO()
        self.application = create_app()
        self.application.state.lookup_order_use_case = LookupOrderUseCase(
            FakeTrackedOrderReader(tracked_order(status)),
            StructlogBusinessEventLogger("basecamp-shop", self.stream),
            FakePseudonymizer(),
        )

    async def lookup(self, payload: Any) -> Any:
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            headers = {"X-Correlation-ID": CORRELATION_ID}
            return await client.post("/orders/lookup", json=payload, headers=headers)


def _body(number: str = NUMBER, email: str = EMAIL) -> dict[str, str]:
    return {"orderNumber": number, "email": email}


class TestOrderLookupRoute:
    async def test_returns_status_lines_and_totals_without_email_or_address(self) -> None:
        response = await _Client().lookup(_body())

        assert response.status_code == 200
        assert response.json() == {
            "number": NUMBER,
            "status": "pending_payment",
            "lines": [
                {
                    "name": "Popote",
                    "unit_price_cents": 3900,
                    "quantity": 2,
                    "line_total_cents": 7800,
                }
            ],
            "subtotal_cents": 7800,
            "shipping_cents": 0,
            "total_cents": 7800,
            "created_at": "2026-10-21T09:30:00Z",
        }
        assert EMAIL not in response.text

    async def test_a_paid_order_is_reported_paid(self) -> None:
        response = await _Client(status="paid").lookup(_body())

        assert response.json()["status"] == "paid"

    async def test_a_wrong_email_and_an_unknown_number_get_the_very_same_404(self) -> None:
        client = _Client()

        wrong_email = await client.lookup(_body(email="intrus@example.org"))
        unknown = await client.lookup(_body(number="BC-ZZZZZZZZZZ"))

        assert wrong_email.status_code == unknown.status_code == 404
        assert wrong_email.content == unknown.content == b'{"detail":"Commande introuvable."}'
        assert dict(wrong_email.headers).keys() == dict(unknown.headers).keys()

    async def test_nothing_the_client_sent_is_reflected(self) -> None:
        client = _Client()

        denied = await client.lookup(_body(email="zz-evil-zz@example.org"))
        invalid = await client.lookup({"orderNumber": "zz-evil-zz", "email": "zz-evil-zz"})

        assert "zz-evil-zz" not in denied.text
        assert invalid.status_code == 422
        assert "zz-evil-zz" not in invalid.text

    async def test_the_order_number_must_have_the_order_format(self) -> None:
        response = await _Client().lookup(_body(number="' OR '1'='1"))

        assert response.status_code == 422

    async def test_extra_fields_and_a_missing_email_are_refused(self) -> None:
        client = _Client()

        assert (await client.lookup({**_body(), "id": "1"})).status_code == 422
        assert (await client.lookup({"orderNumber": NUMBER})).status_code == 422


class TestOrderLookupLogsFollowTheCommonSchema:
    async def test_every_line_is_valid_correlated_and_free_of_the_email(self) -> None:
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        client = _Client()

        await client.lookup(_body())
        await client.lookup(_body(email="intrus@example.org"))
        await client.lookup(_body(number="BC-ZZZZZZZZZZ"))

        raw = client.stream.getvalue()
        records = [json.loads(line) for line in raw.splitlines()]
        assert [r["event"] for r in records] == [
            "order.looked_up",
            "order.lookup_denied",
            "order.lookup_denied",
        ]
        assert [r.get("reason") for r in records] == [None, "email_mismatch", "order_not_found"]
        for record in records:
            validator.validate(record)
            assert record["correlation_id"] == CORRELATION_ID
        assert EMAIL not in raw
        assert "intrus@example.org" not in raw
