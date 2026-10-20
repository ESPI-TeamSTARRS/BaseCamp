import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.core.events.business_event import BusinessEvent
from app.core.logging import correlation
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
FIXED_NOW = datetime(2026, 10, 20, 17, 2, 11, 482000, tzinfo=UTC)


def _emit(event: BusinessEvent) -> tuple[dict[str, Any], str]:
    stream = io.StringIO()
    StructlogBusinessEventLogger("basecamp-payment", stream, lambda: FIXED_NOW).log(event)
    raw = stream.getvalue()
    return json.loads(raw), raw


@pytest.fixture(autouse=True)
def _correlation() -> None:
    correlation.set_correlation_id("7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10")


class TestRenderedLine:
    def test_is_one_json_line_with_the_common_fields(self) -> None:
        record, raw = _emit(BusinessEvent.success("cart.quoted", attributes={"line_count": 3}))

        assert raw.endswith("\n") and raw.count("\n") == 1
        assert record == {
            "timestamp": "2026-10-20T17:02:11.482Z",
            "service": "basecamp-payment",
            "level": "info",
            "event": "cart.quoted",
            "correlation_id": "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10",
            "outcome": "success",
            "attributes": {"line_count": 3},
        }

    def test_level_follows_the_outcome(self) -> None:
        assert _emit(BusinessEvent.denied("a.b", "x"))[0]["level"] == "warning"
        assert _emit(BusinessEvent.error("a.b", "internal_error"))[0]["level"] == "error"

    def test_optional_fields_appear_only_when_set(self) -> None:
        event = BusinessEvent.denied(
            "payment.intent_rejected",
            "amount_exceeds_limit",
            resource_type="payment_intent",
            resource_id="pi_1",
            actor_type="service",
            actor_id="shop",
            duration_ms=12,
            client_ip="203.0.113.7",
        )

        record, _ = _emit(event)

        assert record["reason"] == "amount_exceeds_limit"
        assert (record["resource_type"], record["resource_id"]) == ("payment_intent", "pi_1")
        assert (record["actor_type"], record["actor_id"]) == ("service", "shop")
        assert (record["duration_ms"], record["client_ip"]) == (12, "203.0.113.7")

    def test_a_correlation_id_is_generated_outside_a_request(self) -> None:
        correlation.clear_correlation_id()

        record, _ = _emit(BusinessEvent.success("a.b"))

        assert correlation.is_valid_correlation_id(record["correlation_id"])

    def test_non_utc_clock_is_rendered_in_utc(self) -> None:
        stream = io.StringIO()
        paris = datetime.fromisoformat("2026-10-20T19:02:11.482+02:00")

        StructlogBusinessEventLogger("s", stream, lambda: paris).log(BusinessEvent.success("a.b"))

        assert json.loads(stream.getvalue())["timestamp"] == "2026-10-20T17:02:11.482Z"


class TestSensitiveData:
    def test_sensitive_attribute_keys_never_reach_the_output(self) -> None:
        event = BusinessEvent.success(
            "auth.login_succeeded",
            attributes={
                "password": "Hunter2!",
                "access_token": "eyJhbGciOi.payload.sig",
                "authorization": "Bearer abc",
                "idempotency_key": "idem-aaaa",
                "card_number": "4242424242424242",
                "email_hash": "9f2c1ab07d3e4c55",
            },
        )

        record, raw = _emit(event)

        for secret in ("Hunter2!", "eyJhbGciOi", "Bearer abc", "idem-aaaa", "4242"):
            assert secret not in raw
        assert record["attributes"]["email_hash"] == "9f2c1ab07d3e4c55"

    def test_clear_emails_and_card_numbers_in_values_are_masked(self) -> None:
        event = BusinessEvent.success(
            "a.b",
            resource_type="account",
            resource_id="jean@exemple.fr",
            attributes={"note": "carte 4242 4242 4242 4242 de marie@exemple.fr"},
        )

        _, raw = _emit(event)

        assert "@" not in raw and "4242" not in raw


class TestSchemaConformance:
    @pytest.mark.parametrize(
        "event",
        [
            BusinessEvent.success("catalog.products_listed", attributes={"total": 15}),
            BusinessEvent.denied("cart.quote_rejected", "invalid_cart"),
            BusinessEvent.error("service.unhandled_error", "internal_error"),
            BusinessEvent.denied(
                "auth.login_failed",
                "invalid_credentials",
                actor_type="user",
                actor_id="u1",
                client_ip="203.0.113.7",
                attributes={"email_hash": "9f2c1ab07d3e4c55"},
            ),
        ],
    )
    def test_every_event_validates_against_the_common_schema(self, event: BusinessEvent) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        record, _ = _emit(event)

        Draft202012Validator(schema).validate(record)

    def test_the_schema_rejects_a_refusal_without_reason(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        record, _ = _emit(BusinessEvent.success("a.b"))
        record["outcome"] = "denied"

        assert list(Draft202012Validator(schema).iter_errors(record))
