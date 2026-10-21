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

from app.confirmation.wiring import build_confirmation_services
from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = "tok-shop-test-0001"
CARD_NUMBER = "4242424242424242"
TIMEOUT_SECONDS = 0.5
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


@dataclass
class Env:
    client: TestClient
    engine: Engine
    waits: list[float]
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
    settings = Settings(service_tokens={"shop": TOKEN}, provider_timeout_seconds=TIMEOUT_SECONDS)
    waits: list[float] = []
    log = io.StringIO()
    events = StructlogBusinessEventLogger(settings.service_name, log)
    application = create_app(settings, engine, events)
    application.state.confirmation_services = build_confirmation_services(
        engine, settings, events, waits.append
    )
    with TestClient(application) as client:
        yield Env(client, engine, waits, log)


def _headers(key: str = "confirm-0001") -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}


def _create(env: Env, order: str = "CMD-1") -> str:
    response = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 4990, "currency": "EUR"},
        headers=_headers(f"create-{order}-key"),
    )
    return str(response.json()["id"])


def _confirm(
    env: Env, intent_id: str, method: object = "pm_test_success", key: str = "confirm-0001"
) -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": method},
        headers=_headers(key),
    )
    return response


def _ledger(env: Env) -> list[tuple[str, str, int]]:
    with env.engine.connect() as connection:
        rows = connection.execute(
            text("SELECT account, direction, amount FROM ledger_entries ORDER BY direction")
        )
        return [(row[0], row[1], row[2]) for row in rows]


class TestConfirmation:
    def test_success_marks_the_intent_succeeded_and_writes_two_ledger_entries(
        self, env: Env
    ) -> None:
        intent_id = _create(env)

        response = _confirm(env, intent_id)

        assert response.status_code == 200
        body = response.json()
        assert (body["id"], body["status"], body["amount"]) == (intent_id, "succeeded", 4990)
        assert _ledger(env) == [
            ("marchand", "credit", 4990),
            ("client_attente", "debit", 4990),
        ]

    def test_the_new_status_is_visible_when_reading_the_intent(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm(env, intent_id)

        read = env.client.get(f"/payments/intents/{intent_id}", headers=_headers())

        assert read.json()["status"] == "succeeded"

    def test_a_declined_method_fails_the_intent_without_ledger_entries(self, env: Env) -> None:
        intent_id = _create(env)

        response = _confirm(env, intent_id, "pm_test_declined")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert _ledger(env) == []
        assert env.waits == []

    def test_a_timeout_waits_for_the_bounded_delay_then_fails_the_intent(self, env: Env) -> None:
        intent_id = _create(env)

        response = _confirm(env, intent_id, "pm_test_timeout")

        assert response.json()["status"] == "failed"
        assert env.waits == [TIMEOUT_SECONDS]
        assert _ledger(env) == []


class TestIdempotencyAndConflicts:
    def test_replaying_the_same_key_gives_the_same_result_and_a_single_write(
        self, env: Env
    ) -> None:
        intent_id = _create(env)
        first = _confirm(env, intent_id)

        second = _confirm(env, intent_id)

        assert second.status_code == 200
        assert second.json() == first.json()
        assert len(_ledger(env)) == 2

    def test_another_key_on_a_succeeded_intent_is_a_conflict(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm(env, intent_id)

        response = _confirm(env, intent_id, key="confirm-0002")

        assert response.status_code == 409
        assert len(_ledger(env)) == 2

    def test_the_same_key_with_another_method_is_a_422(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm(env, intent_id)

        response = _confirm(env, intent_id, "pm_test_declined")

        assert response.status_code == 422

    @pytest.mark.parametrize("state", ["expired_by_date", "canceled"])
    def test_an_expired_or_canceled_intent_is_a_conflict(self, env: Env, state: str) -> None:
        intent_id = _create(env)
        statement = (
            "UPDATE payment_intents SET expires_at = '2020-01-01 00:00:00'"
            if state == "expired_by_date"
            else "UPDATE payment_intents SET status = 'canceled'"
        )
        with env.engine.begin() as connection:
            connection.execute(text(statement))

        response = _confirm(env, intent_id)

        assert response.status_code == 409
        assert response.json() == {"detail": "Payment intent cannot be confirmed"}
        assert _ledger(env) == []

    @pytest.mark.parametrize("intent_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"])
    def test_an_unknown_intent_is_a_generic_404(self, env: Env, intent_id: str) -> None:
        response = _confirm(env, intent_id)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}


class TestInputValidation:
    @pytest.mark.parametrize(
        "method",
        [CARD_NUMBER, "pm_card_visa", "", "PM_TEST_SUCCESS", None, 4242, ["pm_test_success"]],
    )
    def test_anything_but_a_test_method_is_a_422_that_never_echoes_the_value(
        self, env: Env, method: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        intent_id = _create(env)
        caplog.set_level(logging.DEBUG)

        response = _confirm(env, intent_id, method)

        assert response.status_code == 422
        assert CARD_NUMBER not in response.text
        assert "pm_card_visa" not in response.text
        assert CARD_NUMBER not in caplog.text
        assert "pm_card_visa" not in caplog.text
        assert _ledger(env) == []

    def test_a_card_number_is_never_logged_or_printed(
        self, env: Env, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        intent_id = _create(env)
        caplog.set_level(logging.DEBUG)

        _confirm(env, intent_id, CARD_NUMBER)

        captured = capsys.readouterr()
        assert CARD_NUMBER not in caplog.text + captured.out + captured.err

    def test_extra_fields_are_refused(self, env: Env) -> None:
        intent_id = _create(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/confirm",
            json={"payment_method": "pm_test_success", "amount": 1},
            headers=_headers(),
        )

        assert response.status_code == 422
        assert _ledger(env) == []

    def test_the_idempotency_key_is_mandatory(self, env: Env) -> None:
        intent_id = _create(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/confirm",
            json={"payment_method": "pm_test_success"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 422

    def test_a_missing_or_invalid_token_is_a_401(self, env: Env) -> None:
        intent_id = _create(env)

        response = env.client.post(
            f"/payments/intents/{intent_id}/confirm",
            json={"payment_method": "pm_test_success"},
            headers={"Idempotency-Key": "confirm-0001"},
        )

        assert response.status_code == 401


def _lines(env: Env) -> list[dict[str, Any]]:
    """Lignes JSON du journal; chacune doit respecter le schéma commun."""
    records = [json.loads(line) for line in env.log.getvalue().splitlines()]
    for record in records:
        errors = [error.message for error in VALIDATOR.iter_errors(record)]
        assert not errors, errors
    return records


def _confirm_logged(env: Env, intent_id: str, method: object, key: str = "confirm-0001") -> None:
    env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": method},
        headers={**_headers(key), "X-Correlation-ID": CORRELATION_ID},
    )


class TestBusinessEvents:
    def test_a_success_logs_valid_correlated_lines_without_secrets(self, env: Env) -> None:
        intent_id = _create(env)
        env.log.truncate(0)
        env.log.seek(0)

        _confirm_logged(env, intent_id, "pm_test_success")

        records = _lines(env)
        assert [r["event"] for r in records] == [
            "payment.service_authenticated",
            "payment.confirmed",
            "ledger.entries_written",
            "webhook.event_queued",
        ]
        assert {r["correlation_id"] for r in records} == {CORRELATION_ID}
        assert records[1]["resource_id"] == intent_id
        raw = env.log.getvalue()
        assert TOKEN not in raw
        assert "confirm-0001" not in raw

    def test_a_decline_and_a_timeout_are_logged_with_their_outcome(self, env: Env) -> None:
        declined, timed_out = _create(env, "CMD-1"), _create(env, "CMD-2")
        env.log.truncate(0)
        env.log.seek(0)

        _confirm_logged(env, declined, "pm_test_declined")
        _confirm_logged(env, timed_out, "pm_test_timeout", "confirm-0002")

        by_event = {r["event"]: r for r in _lines(env)}
        assert (
            by_event["payment.declined"]["outcome"],
            by_event["payment.declined"]["reason"],
        ) == (
            "denied",
            "provider_declined",
        )
        assert (by_event["payment.timeout"]["outcome"], by_event["payment.timeout"]["reason"]) == (
            "error",
            "provider_timeout",
        )

    def test_a_card_number_is_rejected_without_the_value_or_any_secret(self, env: Env) -> None:
        intent_id = _create(env)
        env.log.truncate(0)
        env.log.seek(0)

        _confirm_logged(env, intent_id, CARD_NUMBER)

        rejected = next(r for r in _lines(env) if r["event"] == "payment.confirmation_rejected")
        assert (rejected["outcome"], rejected["reason"]) == ("denied", "invalid_payment_method")
        assert rejected["resource_id"] == intent_id
        assert rejected["correlation_id"] == CORRELATION_ID
        raw = env.log.getvalue()
        assert CARD_NUMBER not in raw
        assert TOKEN not in raw

    def test_a_malformed_intent_id_is_never_echoed(self, env: Env) -> None:
        env.log.truncate(0)
        env.log.seek(0)

        _confirm_logged(env, "secret-looking-id", "bad-method")

        rejected = next(r for r in _lines(env) if r["event"] == "payment.confirmation_rejected")
        assert "resource_id" not in rejected
        assert "secret-looking-id" not in env.log.getvalue()

    def test_a_conflict_is_rejected_with_the_status_as_reason(self, env: Env) -> None:
        intent_id = _create(env)
        _confirm_logged(env, intent_id, "pm_test_success")
        env.log.truncate(0)
        env.log.seek(0)

        _confirm_logged(env, intent_id, "pm_test_success", "confirm-0002")

        rejected = next(r for r in _lines(env) if r["event"] == "payment.confirmation_rejected")
        assert rejected["reason"] == "status_succeeded"
