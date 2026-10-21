import json
from typing import Any

from app.payment_confirmation.domain.entities.payment_event import PaymentEvent
from app.payment_confirmation.domain.errors.invalid_webhook_payload_error import (
    InvalidWebhookPayloadError,
)

_MAX_TEXT = 64
_PAYMENT_PREFIX = "payment."


def parse_payment_event(raw_body: bytes) -> PaymentEvent:
    """Lit le corps publié par `payment`; tout écart de forme est refusé sans écho du contenu."""
    try:
        document = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise InvalidWebhookPayloadError("payload_not_json") from None
    if not isinstance(document, dict):
        raise InvalidWebhookPayloadError("payload_not_object")
    event_id = _text(document.get("id"), "event_id_invalid")
    event_type = _text(document.get("type"), "event_type_invalid")
    data = document.get("data")
    if not isinstance(data, dict):
        raise InvalidWebhookPayloadError("data_invalid")
    created_at = document.get("created_at")
    created = created_at if isinstance(created_at, str) and len(created_at) <= 40 else None
    if event_type.startswith(_PAYMENT_PREFIX):
        return _payment_event(event_id, event_type, created, data)
    other_amount = data.get("amount")
    return PaymentEvent(
        event_id,
        event_type,
        created,
        _optional_text(data.get("order_reference")),
        other_amount
        if isinstance(other_amount, int) and not isinstance(other_amount, bool)
        else None,
        None,
        None,
    )


def _payment_event(
    event_id: str, event_type: str, created_at: str | None, data: dict[str, Any]
) -> PaymentEvent:
    amount = data.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise InvalidWebhookPayloadError("amount_invalid")
    currency = data.get("currency")
    if not isinstance(currency, str) or len(currency) != 3:
        raise InvalidWebhookPayloadError("currency_invalid")
    status = data.get("status")
    return PaymentEvent(
        event_id=event_id,
        event_type=event_type,
        created_at=created_at,
        reference=_text(data.get("order_reference"), "reference_invalid"),
        amount_cents=amount,
        currency=currency,
        status=status if isinstance(status, str) and len(status) <= _MAX_TEXT else None,
    )


def _text(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
        raise InvalidWebhookPayloadError(reason)
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= _MAX_TEXT else None
