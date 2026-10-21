import io
import json
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
    log = io.StringIO()
    settings = Settings(service_tokens={"shop": TOKEN})
    application = create_app(settings, engine, StructlogBusinessEventLogger("payment", log))
    with TestClient(application) as client:
        yield Env(client, engine, log)


def _headers(key: str = "key-00000001", correlation: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}
    return {**headers, "X-Correlation-ID": CORRELATION_ID} if correlation else headers


def _create(env: Env, order: str = "CMD-1") -> str:
    response = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 4990, "currency": "EUR"},
        headers=_headers(f"create-{order}-key"),
    )
    return str(response.json()["id"])


def _cancel(env: Env, intent_id: str, correlation: bool = False) -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/cancel", headers=_headers(correlation=correlation)
    )
    return response


def _confirm(env: Env, intent_id: str, key: str = "confirm-0001") -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": "pm_test_success"},
        headers=_headers(key),
    )
    return response


def _status(env: Env, intent_id: str) -> str:
    return str(env.client.get(f"/payments/intents/{intent_id}", headers=_headers()).json()["status"])


def _ledger_count(env: Env) -> int:
    with env.engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM ledger_entries")).scalar_one())


def _reset_log(env: Env) -> None:
    env.log.truncate(0)
    env.log.seek(0)


def _lines(env: Env) -> list[dict[str, Any]]:
    """Lignes JSON du journal; chacune doit respecter le schéma commun."""
    records = [json.loads(line) for line in env.log.getvalue().splitlines()]
    for record in records:
        errors = [error.message for error in VALIDATOR.iter_errors(record)]
        assert not errors, errors
    return records


class TestCancellation:
    def test_an_unconfirmed_intent_becomes_canceled(self, env: Env) -> None:
        intent_id = _create(env)

        response = _cancel(env, intent_id)

        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["status"], body["amount"]) == (intent_id, "canceled", 4990)
        assert _status(env, intent_id) == "canceled"
        assert _ledger_count(env) == 0

    def test_canceling_twice_gives_the_same_result(self, env: Env) -> None:
        intent_id = _create(env)
        first = _cancel(env, intent_id)

        second = _cancel(env, intent_id)

        assert second.status_code == 200
        assert second.json() == first.json()

    def test_a_canceled_intent_can_no_longer_be_confirmed(self, env: Env) -> None:
        intent_id = _create(env)
        _cancel(env, intent_id)

        response = _confirm(env, intent_id)

        assert response.status_code == 409
        assert _status(env, intent_id) == "canceled"
        assert _ledger_count(env) == 0

    def test_a_confirmed_intent_can_no_longer_be_canceled(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm(env, intent_id)

        response = _cancel(env, intent_id)

        assert response.status_code == 409
        assert response.json() == {"detail": "Payment intent cannot be canceled"}
        assert _status(env, intent_id) == "succeeded"
        assert _ledger_count(env) == 2

    @pytest.mark.parametrize("state", ["failed", "expired"])
    def test_a_failed_or_expired_intent_cannot_be_canceled(self, env: Env, state: str) -> None:
        intent_id = _create(env)
        with env.engine.begin() as connection:
            connection.execute(text(f"UPDATE payment_intents SET status = '{state}'"))  # noqa: S608

        response = _cancel(env, intent_id)

        assert response.status_code == 409
        assert _status(env, intent_id) == state

    def test_an_intent_past_its_deadline_cannot_be_canceled(self, env: Env) -> None:
        intent_id = _create(env)
        with env.engine.begin() as connection:
            connection.execute(text("UPDATE payment_intents SET expires_at = '2020-01-01 00:00:00'"))

        response = _cancel(env, intent_id)

        assert response.status_code == 409
        assert _status(env, intent_id) == "requires_confirmation"

    @pytest.mark.parametrize("intent_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"])
    def test_an_unknown_intent_is_a_generic_404(self, env: Env, intent_id: str) -> None:
        response = _cancel(env, intent_id)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}

    def test_a_missing_or_invalid_token_is_a_401(self, env: Env) -> None:
        intent_id = _create(env)

        missing = env.client.post(f"/payments/intents/{intent_id}/cancel")
        invalid = env.client.post(
            f"/payments/intents/{intent_id}/cancel", headers={"Authorization": "Bearer nope"}
        )

        assert (missing.status_code, invalid.status_code) == (401, 401)
        assert _status(env, intent_id) == "requires_confirmation"


class TestBusinessEvents:
    def test_a_cancellation_logs_a_valid_correlated_line_without_secrets(self, env: Env) -> None:
        intent_id = _create(env)
        _reset_log(env)

        _cancel(env, intent_id, correlation=True)

        records = _lines(env)
        assert [r["event"] for r in records] == ["payment.service_authenticated", "payment.canceled"]
        canceled = records[1]
        assert (canceled["outcome"], canceled["level"]) == ("success", "info")
        assert (canceled["resource_type"], canceled["resource_id"]) == ("payment_intent", intent_id)
        assert canceled["attributes"] == {
            "order_reference": "CMD-1",
            "amount_cents": 4990,
            "currency": "EUR",
        }
        assert {r["correlation_id"] for r in records} == {CORRELATION_ID}
        assert TOKEN not in env.log.getvalue()

    def test_a_conflict_is_rejected_with_the_status_as_reason(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm(env, intent_id)
        _reset_log(env)

        _cancel(env, intent_id, correlation=True)

        rejected = next(r for r in _lines(env) if r["event"] == "payment.cancellation_rejected")
        assert (rejected["outcome"], rejected["reason"]) == ("denied", "status_succeeded")
        assert rejected["resource_id"] == intent_id

    def test_a_malformed_intent_id_is_never_echoed(self, env: Env) -> None:
        _reset_log(env)

        _cancel(env, "secret-looking-id", correlation=True)

        rejected = next(r for r in _lines(env) if r["event"] == "payment.cancellation_rejected")
        assert rejected["reason"] == "intent_not_found"
        assert "resource_id" not in rejected
        assert "secret-looking-id" not in env.log.getvalue()
