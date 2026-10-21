import io
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event, text

from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = "tok-shop-test-0001"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
CAPTURED = 10000


@dataclass
class Env:
    client: TestClient
    engine: Engine
    log: io.StringIO


@pytest.fixture
def env() -> Iterator[Env]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings(service_tokens={"shop": TOKEN}, provider_timeout_seconds=0.1)
    log = io.StringIO()
    events = StructlogBusinessEventLogger(settings.service_name, log)
    with TestClient(create_app(settings, engine, events)) as client:
        yield Env(client, engine, log)


def _headers(key: str = "refund-0001") -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}


def _paid_intent(env: Env, order: str = "CMD-1", method: str = "pm_test_success") -> str:
    created = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": CAPTURED, "currency": "EUR"},
        headers=_headers(f"create-{order}-key"),
    )
    intent_id = str(created.json()["id"])
    env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": method},
        headers=_headers(f"confirm-{order}-key"),
    )
    return intent_id


def _refund(env: Env, intent_id: str, amount: object = 4000, key: str = "refund-0001") -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/refunds", json={"amount": amount}, headers=_headers(key)
    )
    return response


def _rows(env: Env, sql: str) -> list[tuple[Any, ...]]:
    with env.engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


def _refunded(env: Env, intent_id: str) -> int:
    response = env.client.get(f"/payments/intents/{intent_id}", headers=_headers())
    return int(response.json()["refunded_amount"])


def _refund_ledger(env: Env) -> list[tuple[str, str, int]]:
    return [
        (str(a), str(d), int(m))
        for a, d, m in _rows(
            env,
            "SELECT account, direction, amount FROM ledger_entries "
            "WHERE account IN ('remboursements') OR transaction_id IN "
            "(SELECT transaction_id FROM ledger_entries WHERE account = 'remboursements') "
            "ORDER BY direction",
        )
    ]


class TestRefund:
    def test_a_partial_refund_is_created_with_two_inverse_ledger_entries(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, intent_id, 4000)

        assert response.status_code == 201
        body = response.json()
        assert body["amount"] == 4000
        assert body["amount_refunded"] == 4000
        assert (body["payment_intent_id"], body["currency"], body["status"]) == (
            intent_id,
            "EUR",
            "succeeded",
        )
        assert _refunded(env, intent_id) == 4000
        assert _refund_ledger(env) == [
            ("remboursements", "credit", 4000),
            ("marchand", "debit", 4000),
        ]

    def test_the_refund_is_stored_and_the_event_is_queued_in_the_outbox(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        refund_id = _refund(env, intent_id).json()["id"]

        assert _rows(env, "SELECT id, intent_id, amount, amount_refunded FROM refunds") == [
            (refund_id.replace("-", ""), intent_id.replace("-", ""), 4000, 4000)
        ]
        assert _rows(env, "SELECT event_type, status FROM outbox ORDER BY created_at") == [
            ("payment.succeeded", "pending"),
            ("refund.succeeded", "pending"),
        ]

    def test_4000_then_6001_is_a_conflict_but_6000_succeeds(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _refund(env, intent_id, 4000)

        too_much = _refund(env, intent_id, 6001, "refund-0002")
        exact = _refund(env, intent_id, 6000, "refund-0003")

        assert too_much.status_code == 409
        assert too_much.json() == {"detail": "Refund exceeds the captured amount"}
        assert exact.status_code == 201
        assert exact.json()["amount_refunded"] == CAPTURED
        assert _refunded(env, intent_id) == CAPTURED
        assert len(_rows(env, "SELECT 1 FROM refunds")) == 2

    def test_a_fully_refunded_intent_accepts_nothing_more(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _refund(env, intent_id, CAPTURED)

        response = _refund(env, intent_id, 1, "refund-0002")

        assert response.status_code == 409


class TestIdempotency:
    def test_replaying_the_same_key_returns_the_same_refund_and_writes_once(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        first = _refund(env, intent_id)

        second = _refund(env, intent_id)

        assert second.status_code == 200
        assert second.json() == first.json()
        assert _refunded(env, intent_id) == 4000
        assert len(_refund_ledger(env)) == 2
        assert len(_rows(env, "SELECT 1 FROM refunds")) == 1
        assert len(_rows(env, "SELECT 1 FROM outbox WHERE event_type = 'refund.succeeded'")) == 1

    def test_the_same_key_with_another_amount_is_a_422(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _refund(env, intent_id, 4000)

        response = _refund(env, intent_id, 1000)

        assert response.status_code == 422
        assert response.json() == {"detail": "Idempotency key already used with another request"}
        assert _refunded(env, intent_id) == 4000

    def test_the_same_key_for_another_intent_is_a_422(self, env: Env) -> None:
        first, second = _paid_intent(env, "CMD-1"), _paid_intent(env, "CMD-2")
        _refund(env, first)

        response = _refund(env, second)

        assert response.status_code == 422
        assert _refunded(env, second) == 0


class TestRefusedRefund:
    @pytest.mark.parametrize("method", ["pm_test_declined", "pm_test_timeout"])
    def test_a_failed_intent_is_a_conflict(self, env: Env, method: str) -> None:
        intent_id = _paid_intent(env, method=method)

        response = _refund(env, intent_id)

        assert response.status_code == 409
        assert response.json() == {"detail": "Payment intent cannot be refunded"}
        assert _rows(env, "SELECT 1 FROM refunds") == []

    def test_an_intent_awaiting_confirmation_is_a_conflict(self, env: Env) -> None:
        created = env.client.post(
            "/payments/intents",
            json={"order_reference": "CMD-9", "amount": CAPTURED, "currency": "EUR"},
            headers=_headers("create-0009"),
        )

        response = _refund(env, str(created.json()["id"]))

        assert response.status_code == 409

    def test_a_canceled_intent_is_a_conflict(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        with env.engine.begin() as connection:
            connection.execute(text("UPDATE payment_intents SET status = 'canceled'"))

        assert _refund(env, intent_id).status_code == 409

    @pytest.mark.parametrize("intent_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"])
    def test_an_unknown_intent_is_a_generic_404(self, env: Env, intent_id: str) -> None:
        response = _refund(env, intent_id)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}


class TestInputValidation:
    @pytest.mark.parametrize("amount", [0, -1, -4000, 40.5, 4000.0, "4000", True, None, [4000]])
    def test_a_non_positive_decimal_or_non_integer_amount_is_a_422(
        self, env: Env, amount: object
    ) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, intent_id, amount)

        assert response.status_code == 422
        assert _refunded(env, intent_id) == 0
        assert _rows(env, "SELECT 1 FROM refunds") == []

    def test_a_missing_amount_is_a_422(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/refunds", json={}, headers=_headers()
        )

        assert response.status_code == 422

    def test_extra_fields_are_refused(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/refunds",
            json={"amount": 100, "currency": "EUR"},
            headers=_headers(),
        )

        assert response.status_code == 422

    def test_the_422_never_echoes_the_received_value(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, intent_id, "4242424242424242")

        assert response.status_code == 422
        assert "4242" not in response.text

    def test_the_idempotency_key_is_mandatory(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/refunds",
            json={"amount": 100},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 422

    def test_a_missing_or_invalid_token_is_a_401(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/refunds",
            json={"amount": 100},
            headers={"Idempotency-Key": "refund-0001"},
        )

        assert response.status_code == 401


class TestFraud:
    def test_replaying_a_refund_many_times_never_refunds_twice(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        statuses = [_refund(env, intent_id, 6000).status_code for _ in range(10)]

        assert statuses == [201, *[200] * 9]
        assert _refunded(env, intent_id) == 6000
        assert len(_rows(env, "SELECT 1 FROM refunds")) == 1
        assert len(_refund_ledger(env)) == 2

    def test_new_keys_cannot_push_the_total_above_the_captured_amount(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        statuses = [_refund(env, intent_id, 3000, f"refund-{n:04d}").status_code for n in range(6)]

        assert statuses == [201, 201, 201, 409, 409, 409]
        assert _refunded(env, intent_id) == 9000
        (total,) = _rows(env, "SELECT SUM(amount) FROM refunds")[0]
        assert total <= CAPTURED
        debits = _rows(
            env,
            "SELECT SUM(amount) FROM ledger_entries "
            "WHERE account = 'marchand' AND direction = 'debit'",
        )
        assert debits == [(9000,)]

    def test_changing_the_amount_under_a_used_key_is_refused_without_a_write(
        self, env: Env
    ) -> None:
        intent_id = _paid_intent(env)
        _refund(env, intent_id, 1000)

        statuses = [_refund(env, intent_id, amount).status_code for amount in (999, 1001, 10000)]

        assert statuses == [422, 422, 422]
        assert _refunded(env, intent_id) == 1000

    def test_a_forged_amount_above_the_database_ceiling_is_rejected_without_a_500(
        self, env: Env
    ) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, intent_id, 10**30)

        assert response.status_code in (409, 422)
        assert _refunded(env, intent_id) == 0


def _lines(env: Env) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in env.log.getvalue().splitlines()]
    for record in records:
        errors = [error.message for error in VALIDATOR.iter_errors(record)]
        assert not errors, errors
    return records


def _reset_log(env: Env) -> None:
    env.log.truncate(0)
    env.log.seek(0)


def _refund_logged(env: Env, intent_id: str, amount: object, key: str = "refund-0001") -> None:
    env.client.post(
        f"/payments/intents/{intent_id}/refunds",
        json={"amount": amount},
        headers={**_headers(key), "X-Correlation-ID": CORRELATION_ID},
    )


class TestBusinessEvents:
    def test_a_refund_logs_valid_correlated_lines_without_secrets(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _reset_log(env)

        _refund_logged(env, intent_id, 4000)

        records = _lines(env)
        assert [r["event"] for r in records] == [
            "payment.service_authenticated",
            "refund.succeeded",
            "ledger.entries_written",
            "webhook.event_queued",
        ]
        assert {r["correlation_id"] for r in records} == {CORRELATION_ID}
        refunded = records[1]
        assert (refunded["resource_type"], refunded["outcome"]) == ("refund", "success")
        assert refunded["attributes"]["amount_refunded_cents"] == 4000
        raw = env.log.getvalue()
        assert TOKEN not in raw
        assert "refund-0001" not in raw

    def test_an_excess_is_logged_as_a_denied_event(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _refund_logged(env, intent_id, 4000)
        _reset_log(env)

        _refund_logged(env, intent_id, 6001, "refund-0002")

        rejected = next(r for r in _lines(env) if r["event"] == "refund.rejected")
        assert (rejected["outcome"], rejected["reason"]) == ("denied", "amount_exceeds_refundable")
        assert rejected["resource_id"] == intent_id
        assert rejected["attributes"]["refundable_cents"] == 6000
        assert "refund-0002" not in env.log.getvalue()

    def test_an_invalid_amount_is_rejected_without_the_value(self, env: Env) -> None:
        intent_id = _paid_intent(env)
        _reset_log(env)

        _refund_logged(env, intent_id, "4242424242424242")

        rejected = next(r for r in _lines(env) if r["event"] == "refund.rejected")
        assert (rejected["outcome"], rejected["reason"]) == ("denied", "invalid_request")
        assert rejected["resource_id"] == intent_id
        assert rejected["correlation_id"] == CORRELATION_ID
        assert "4242" not in env.log.getvalue()

    def test_a_malformed_intent_id_is_never_echoed(self, env: Env) -> None:
        _reset_log(env)

        _refund_logged(env, "secret-looking-id", "bad-amount")

        rejected = next(r for r in _lines(env) if r["event"] == "refund.rejected")
        assert "resource_id" not in rejected
        assert "secret-looking-id" not in env.log.getvalue()

    def test_nothing_sensitive_reaches_the_technical_logs(
        self, env: Env, caplog: pytest.LogCaptureFixture
    ) -> None:
        intent_id = _paid_intent(env)
        caplog.set_level(logging.DEBUG)

        _refund(env, intent_id, "4242424242424242")
        _refund(env, intent_id, 4000)

        assert "4242424242424242" not in caplog.text
        assert TOKEN not in caplog.text
