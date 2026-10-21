"""Lecture du corps publié par payment (docs/services/payment.md, « Format publié »)."""

import json
from typing import Any

import pytest

from app.payment_confirmation.domain.entities.payment_event import PaymentEvent
from app.payment_confirmation.domain.errors.invalid_webhook_payload_error import (
    InvalidWebhookPayloadError,
)
from app.payment_confirmation.domain.services.payment_event_parser import parse_payment_event

EVENT_ID = "0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11"


def _body(**overrides: Any) -> bytes:
    document: dict[str, Any] = {
        "id": EVENT_ID,
        "type": "payment.succeeded",
        "created_at": "2026-10-21T09:00:00.123Z",
        "data": {
            "payment_intent_id": "7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42",
            "order_reference": "BC-ABCDEFGHJK",
            "amount": 4490,
            "currency": "EUR",
            "status": "succeeded",
        },
    }
    document.update(overrides)
    return json.dumps(document).encode()


class TestParsePaymentEvent:
    def test_reads_a_payment_event(self) -> None:
        assert parse_payment_event(_body()) == PaymentEvent(
            event_id=EVENT_ID,
            event_type="payment.succeeded",
            created_at="2026-10-21T09:00:00.123Z",
            reference="BC-ABCDEFGHJK",
            amount_cents=4490,
            currency="EUR",
            status="succeeded",
        )

    def test_a_refund_event_is_read_without_payment_only_fields(self) -> None:
        body = _body(
            type="refund.succeeded",
            data={"refund_id": "r-1", "order_reference": "BC-ABCDEFGHJK", "amount": 100},
        )

        event = parse_payment_event(body)

        assert (event.event_type, event.reference, event.amount_cents) == (
            "refund.succeeded",
            "BC-ABCDEFGHJK",
            100,
        )

    @pytest.mark.parametrize(
        "body",
        [
            b"",
            b"pas du json",
            b"[]",
            b'"texte"',
            _body(id=""),
            _body(id=12),
            _body(id="x" * 65),
            _body(type=None),
            _body(type="payment.succeeded", data=None),
            _body(data={"order_reference": "BC-1", "amount": "4490", "currency": "EUR"}),
            _body(data={"order_reference": "BC-1", "amount": True, "currency": "EUR"}),
            _body(data={"order_reference": "BC-1", "amount": -1, "currency": "EUR"}),
            _body(data={"order_reference": "BC-1", "amount": 10, "currency": "EURO"}),
            _body(data={"order_reference": 7, "amount": 10, "currency": "EUR"}),
            _body(data={"amount": 10, "currency": "EUR"}),
            b"\xff\xfe",
        ],
    )
    def test_rejects_a_malformed_body(self, body: bytes) -> None:
        with pytest.raises(InvalidWebhookPayloadError):
            parse_payment_event(body)
