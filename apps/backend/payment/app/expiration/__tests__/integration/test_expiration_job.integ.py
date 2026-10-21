import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event, text

from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.expiration.presentation.cli import main
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = "tok-shop-test-0001"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
PAST = "2020-01-01 00:00:00"


@dataclass
class Env:
    client: TestClient
    engine: Engine
    settings: Settings
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
    settings = Settings(service_tokens={"shop": TOKEN}, expiration_batch_size=2)
    log = io.StringIO()
    application = create_app(settings, engine, StructlogBusinessEventLogger("payment", log))
    with TestClient(application) as client:
        yield Env(client, engine, settings, log)


def _headers(key: str = "key-00000001") -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}


def _create(env: Env, order: str) -> str:
    response = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 4990, "currency": "EUR"},
        headers=_headers(f"create-{order}-key"),
    )
    return str(response.json()["id"])


def _confirm(env: Env, intent_id: str) -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": "pm_test_success"},
        headers=_headers("confirm-0001"),
    )
    return response


def _status(env: Env, intent_id: str) -> str:
    return str(
        env.client.get(f"/payments/intents/{intent_id}", headers=_headers()).json()["status"]
    )


def _set_deadline(env: Env, intent_id: str, when: str) -> None:
    with env.engine.begin() as connection:
        connection.execute(
            text("UPDATE payment_intents SET expires_at = :when WHERE id = :id"),
            {"when": when, "id": intent_id.replace("-", "")},
        )


def _ledger_count(env: Env) -> int:
    with env.engine.connect() as connection:
        return int(connection.execute(text("SELECT count(*) FROM ledger_entries")).scalar_one())


def _run(env: Env) -> list[dict[str, Any]]:
    """Exécute le traitement d'expiration et renvoie ses lignes de journal, validées."""
    env.log.truncate(0)
    env.log.seek(0)
    assert main(env.settings, env.engine, StructlogBusinessEventLogger("payment", env.log)) == 0
    records = [json.loads(line) for line in env.log.getvalue().splitlines()]
    for record in records:
        errors = [error.message for error in VALIDATOR.iter_errors(record)]
        assert not errors, errors
    return records


class TestExpirationJob:
    def test_overdue_unconfirmed_intents_expire_without_any_ledger_entry(self, env: Env) -> None:
        overdue, fresh = _create(env, "CMD-1"), _create(env, "CMD-2")
        _set_deadline(env, overdue, PAST)

        _run(env)

        assert (_status(env, overdue), _status(env, fresh)) == (
            "expired",
            "requires_confirmation",
        )
        assert _ledger_count(env) == 0

    def test_default_deadline_is_thirty_minutes_after_creation(self, env: Env) -> None:
        intent_id = _create(env, "CMD-1")
        body = env.client.get(f"/payments/intents/{intent_id}", headers=_headers()).json()
        created = datetime.fromisoformat(body["created_at"])
        expires = datetime.fromisoformat(body["expires_at"])

        assert expires - created == timedelta(minutes=30)
        assert Settings().intent_ttl_minutes == 30

    def test_settled_and_canceled_intents_are_left_alone(self, env: Env) -> None:
        confirmed, canceled = _create(env, "CMD-1"), _create(env, "CMD-2")
        _confirm(env, confirmed)
        env.client.post(f"/payments/intents/{canceled}/cancel", headers=_headers())
        for intent_id in (confirmed, canceled):
            _set_deadline(env, intent_id, PAST)

        _run(env)

        assert (_status(env, confirmed), _status(env, canceled)) == ("succeeded", "canceled")
        assert _ledger_count(env) == 2

    def test_a_second_run_has_no_second_effect(self, env: Env) -> None:
        for n in range(5):
            _set_deadline(env, _create(env, f"CMD-{n}"), PAST)

        first = _run(env)
        second = _run(env)

        assert [r["event"] for r in first].count("payment.expired") == 5
        assert second == []

    def test_an_expired_intent_can_neither_be_confirmed_nor_canceled(self, env: Env) -> None:
        intent_id = _create(env, "CMD-1")
        _set_deadline(env, intent_id, PAST)
        _run(env)

        confirm = _confirm(env, intent_id)
        cancel = env.client.post(f"/payments/intents/{intent_id}/cancel", headers=_headers())

        assert (confirm.status_code, cancel.status_code) == (409, 409)
        assert _status(env, intent_id) == "expired"
        assert _ledger_count(env) == 0

    def test_events_follow_the_common_schema_without_secrets(self, env: Env) -> None:
        intent_id = _create(env, "CMD-1")
        _set_deadline(env, intent_id, PAST)

        records = _run(env)

        assert [r["event"] for r in records] == ["payment.expired", "payment.expiration_completed"]
        expired, completed = records
        assert (expired["outcome"], expired["level"]) == ("success", "info")
        assert (expired["resource_type"], expired["resource_id"]) == ("payment_intent", intent_id)
        assert completed["attributes"] == {"expired_count": 1}
        assert expired["correlation_id"] == completed["correlation_id"]
        assert TOKEN not in env.log.getvalue()
        assert "create-CMD-1-key" not in env.log.getvalue()
