import io
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event

from app.caller_identity.__tests__.tokens import SHOP_TOKEN
from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = SHOP_TOKEN
IDEMPOTENCY_KEY = "create-secret-key-0001"
ORDER = "CMD-PRIVATE-0001"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


@dataclass
class Env:
    client: TestClient
    engine: Engine
    log: io.StringIO
    application: FastAPI

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.getvalue().splitlines()]

    def metrics(self) -> str:
        response = self.client.get("/metrics")
        assert response.status_code == 200
        return str(response.text)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    return engine


@pytest.fixture
def env() -> Iterator[Env]:
    engine = _engine()
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings()
    log = io.StringIO()
    application = create_app(
        settings, engine, StructlogBusinessEventLogger(settings.service_name, log)
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        yield Env(client, engine, log, application)


def _create(env: Env, order: str = ORDER) -> Any:
    return env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 4990, "currency": "EUR"},
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Idempotency-Key": IDEMPOTENCY_KEY,
            "X-Correlation-ID": CORRELATION_ID,
        },
    )


class TestMetricsEndpoint:
    def test_it_answers_in_the_prometheus_text_format_without_credentials(self, env: Env) -> None:
        response = env.client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
        assert "# TYPE payment_http_requests_total counter" in response.text
        assert "payment_state_up 1" in response.text

    def test_requests_are_counted_by_route_template_method_and_status(self, env: Env) -> None:
        _create(env)

        text = env.metrics()

        assert (
            'payment_http_requests_total{route="/payments/intents",method="POST",status="201"} 1'
            in text
        )
        assert re.search(
            r'payment_http_request_duration_seconds_count\{route="/payments/intents",method="POST"\} 1',
            text,
        )

    def test_denials_are_visible_per_status(self, env: Env) -> None:
        env.client.post("/payments/intents", json={})
        env.client.get("/payments/intents/not-a-uuid", headers={"Authorization": "Bearer nope"})

        text = env.metrics()

        assert 'route="/payments/intents",method="POST",status="401"} 1' in text
        assert 'route="/payments/intents/{intent_id}",method="GET",status="401"} 1' in text

    def test_state_gauges_follow_the_database(self, env: Env) -> None:
        _create(env)

        text = env.metrics()

        assert 'payment_intents{status="requires_confirmation"} 1' in text
        assert 'payment_webhook_events{status="pending"} 0' in text
        assert 'payment_ledger_discrepancies{kind="amount_mismatch"} 0' in text

    def test_an_unreachable_database_degrades_to_state_down_not_to_an_error(self) -> None:
        settings = Settings()
        application = create_app(settings, _engine())  # aucune table

        with TestClient(application) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert "payment_state_up 0" in response.text


class TestNoSensitiveLabel:
    def test_neither_identifiers_nor_secrets_nor_raw_paths_reach_the_series(self, env: Env) -> None:
        intent_id = _create(env).json()["id"]
        env.client.get(
            f"/payments/intents/{intent_id}", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        env.client.get(f"/payments/intents?order_reference={ORDER}")
        env.client.get("/does/not/exist/7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10?card=4242424242424242")

        text = env.metrics()

        for forbidden in (TOKEN, IDEMPOTENCY_KEY, ORDER, intent_id, "does/not/exist"):
            assert forbidden not in text
        # Le numéro de carte de la requête ne doit atteindre aucune étiquette. Les valeurs des échantillons
        # (durées, avec leurs 16 chiffres) peuvent contenir « 4242 » par hasard : seules les étiquettes comptent.
        labels = " ".join(re.findall(r"\{([^}]*)\}", text))
        assert "4242" not in labels
        assert "card=" not in text
        assert 'route="/payments/intents/{intent_id}"' in text
        assert 'route="unmatched",method="GET",status="404"' in text

    def test_every_label_name_is_from_the_closed_list(self, env: Env) -> None:
        _create(env)

        names = set(re.findall(r"([a-z_]+)=\"", env.metrics()))

        assert names <= {"route", "method", "status", "le", "kind"}


class TestProxiedRequestsAreRefused:
    @pytest.mark.parametrize(
        "header",
        ["X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded", "X-Real-Ip"],
    )
    def test_a_request_carrying_proxy_headers_is_a_404_and_a_logged_denial(
        self, env: Env, header: str
    ) -> None:
        response = env.client.get("/metrics", headers={header: "203.0.113.9"})

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}
        assert "payment_" not in response.text
        refusal = [line for line in env.lines() if line["event"] == "service.metrics_refused"]
        assert len(refusal) == 1
        assert refusal[0]["outcome"] == "denied"
        assert refusal[0]["reason"] == "proxied_request"

    def test_the_refusal_is_still_counted_as_a_404(self, env: Env) -> None:
        env.client.get("/metrics", headers={"X-Forwarded-For": "203.0.113.9"})

        assert 'route="/metrics",method="GET",status="404"} 1' in env.metrics()


class TestRequestLogLines:
    def test_a_request_logs_route_status_latency_caller_and_request_id(self, env: Env) -> None:
        _create(env)

        (line,) = [x for x in env.lines() if x["event"] == "service.request_completed"]

        assert line["correlation_id"] == CORRELATION_ID
        assert line["outcome"] == "success"
        assert line["attributes"] == {"route": "/payments/intents", "method": "POST", "status": 201}
        assert isinstance(line["duration_ms"], int)
        assert line["duration_ms"] >= 0
        assert (line["actor_type"], line["actor_id"]) == ("service", "shop")

    def test_every_line_respects_the_common_schema(self, env: Env) -> None:
        _create(env)
        env.client.post("/payments/intents", json={})
        env.client.get("/nope")

        lines = env.lines()

        assert lines
        for line in lines:
            VALIDATOR.validate(line)

    def test_a_denied_request_is_a_warning_with_the_status_as_reason(self, env: Env) -> None:
        env.client.post("/payments/intents", json={})

        (line,) = [x for x in env.lines() if x["event"] == "service.request_completed"]

        assert (line["level"], line["reason"]) == ("warning", "http_401")
        assert "actor_id" not in line

    def test_no_secret_reaches_the_request_log(self, env: Env) -> None:
        _create(env)

        raw = env.log.getvalue()

        for forbidden in (TOKEN, IDEMPOTENCY_KEY):
            assert forbidden not in raw

    def test_probes_do_not_flood_the_log(self, env: Env) -> None:
        env.client.get("/health")
        env.client.get("/health/ready")
        env.client.get("/metrics")

        assert [x for x in env.lines() if x["event"] == "service.request_completed"] == []

    def test_an_unhandled_error_is_logged_as_a_500_and_counted(self, env: Env) -> None:
        def boom() -> None:
            raise RuntimeError("detail interne")

        env.application.add_api_route("/boom", boom)

        response = env.client.get("/boom")

        assert response.status_code == 500
        (line,) = [x for x in env.lines() if x["event"] == "service.request_completed"]
        assert (line["outcome"], line["reason"]) == ("error", "http_500")
        assert 'route="/boom",method="GET",status="500"} 1' in env.metrics()
