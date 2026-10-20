import json
from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from app.core.config import Settings
from app.intent.infrastructure.models.base import Base
from app.intent.wiring import build_intent_services
from app.main import create_app

TOKEN = "tok-shop-test-0001"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "key-0001"}
BODY = {"order_reference": "CMD-1", "amount": 2500, "currency": "EUR"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    application = create_app()
    settings = Settings(service_tokens={"shop": TOKEN})
    application.state.intent_services = build_intent_services(
        engine, settings, application.state.events
    )
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


def _records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]


class TestPaymentLogging:
    def test_a_creation_writes_correlated_authentication_and_creation_lines(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()

        response = client.post(
            "/payments/intents",
            json=BODY,
            headers={**HEADERS, "X-Correlation-ID": CORRELATION_ID},
        )

        records = _records(capsys)
        assert response.status_code == 201
        assert response.headers["X-Correlation-ID"] == CORRELATION_ID
        assert [r["event"] for r in records] == [
            "payment.service_authenticated",
            "payment.intent_created",
        ]
        assert {r["correlation_id"] for r in records} == {CORRELATION_ID}
        assert {r["service"] for r in records} == {"basecamp-payment"}

    def test_a_bad_token_logs_a_denied_event_with_the_forwarded_ip_and_no_secret(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()

        response = client.post(
            "/payments/intents",
            json=BODY,
            headers={
                "Authorization": "Bearer wrong-token-value",
                "Idempotency-Key": "key-0001",
                "X-Forwarded-For": "203.0.113.7, 10.0.0.2",
            },
        )

        out = capsys.readouterr().out
        (record,) = [json.loads(line) for line in out.strip().splitlines()]
        assert response.status_code == 401
        assert (record["event"], record["reason"], record["client_ip"]) == (
            "payment.service_authenticated",
            "invalid_token",
            "203.0.113.7",
        )
        assert "wrong-token-value" not in out and "key-0001" not in out

    def test_a_forged_forwarded_address_is_not_logged(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()

        client.post(
            "/payments/intents",
            json=BODY,
            headers={
                "Authorization": "Bearer nope-nope",
                "Idempotency-Key": "key-0001",
                "X-Forwarded-For": "<script>alert(1)</script>",
            },
        )

        (record,) = _records(capsys)
        assert "client_ip" not in record or "script" not in str(record["client_ip"])

    def test_a_refused_creation_logs_a_denied_event(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()

        response = client.post(
            "/payments/intents", json={**BODY, "amount": 600_000}, headers=HEADERS
        )

        records = _records(capsys)
        assert response.status_code == 422
        assert (records[-1]["event"], records[-1]["reason"]) == (
            "payment.intent_rejected",
            "amount_exceeds_limit",
        )

    def test_an_invalid_body_logs_request_rejected_without_the_input(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        capsys.readouterr()

        response = client.post(
            "/payments/intents", json={**BODY, "currency": "<script>"}, headers=HEADERS
        )

        out = capsys.readouterr().out
        assert response.status_code == 422
        assert "service.request_rejected" in out and "<script>" not in out

    def test_an_unexpected_error_logs_a_sanitized_error_event(
        self, client: TestClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        application = cast(FastAPI, client.app)

        @application.get("/boom")
        def boom() -> None:
            raise RuntimeError("postgres://u:secret@h/db")

        capsys.readouterr()
        response = client.get("/boom", headers={"X-Correlation-ID": CORRELATION_ID})

        out = capsys.readouterr().out
        assert response.status_code == 500
        assert response.json() == {"detail": "Erreur interne."}
        assert "service.unhandled_error" in out and "secret" not in out
