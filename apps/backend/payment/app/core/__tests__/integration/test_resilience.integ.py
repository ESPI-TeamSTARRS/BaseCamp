"""Tenue en charge et sous attaque, de bout en bout dans le processus (ASGI, base SQLite)."""

import asyncio
import dataclasses
import io
import json
import time
import uuid
from pathlib import Path
from typing import Any

import jsonschema
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.caller_identity.__tests__.tokens import ADMIN_TOKEN, SHOP_TOKEN
from app.core.config import Settings
from app.core.events import service_event_names as names
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base as IntentBase
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = SHOP_TOKEN
OTHER_TOKEN = ADMIN_TOKEN
CARD = "4242424242424242"
SHOP = {"Authorization": f"Bearer {TOKEN}"}
ADMIN = {"Authorization": f"Bearer {OTHER_TOKEN}"}


def _engine() -> Any:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    IntentBase.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    return engine


def _app(engine: Any = None, **overrides: Any) -> FastAPI:
    settings = Settings(**overrides)
    return create_app(settings, engine or _engine())


def _client(application: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


def _create_headers(token_headers: dict[str, str], key: str | None = None) -> dict[str, str]:
    return {**token_headers, "Idempotency-Key": key or f"key-{uuid.uuid4().hex}"}


def _body(reference: str | None = None) -> dict[str, Any]:
    return {
        "order_reference": reference or f"CMD-{uuid.uuid4().hex[:10]}",
        "amount": 2500,
        "currency": "EUR",
    }


class TestBodySize:
    async def test_oversized_body_gets_413_before_any_processing(self) -> None:
        async with _client(_app(max_body_bytes=1024)) as client:
            response = await client.post(
                "/payments/intents", content=b"x" * 2048, headers=_create_headers(SHOP)
            )

        assert response.status_code == 413
        assert response.json() == {"detail": "Payload too large"}

    async def test_chunked_oversized_body_gets_413(self) -> None:
        async def chunks() -> Any:
            for _ in range(10):
                yield b"y" * 512

        async with _client(_app(max_body_bytes=1024)) as client:
            response = await client.post(
                "/payments/intents", content=chunks(), headers=_create_headers(SHOP)
            )

        assert response.status_code == 413

    async def test_normal_body_still_works(self) -> None:
        async with _client(_app()) as client:
            response = await client.post(
                "/payments/intents", json=_body(), headers=_create_headers(SHOP)
            )

        assert response.status_code == 201


class TestRateLimit:
    async def test_over_the_limit_gets_429_with_retry_after(self) -> None:
        async with _client(_app(rate_limit_create_per_window=2)) as client:
            statuses = [
                (
                    await client.post(
                        "/payments/intents", json=_body(), headers=_create_headers(SHOP)
                    )
                )
                for _ in range(3)
            ]

        assert [r.status_code for r in statuses] == [201, 201, 429]
        assert statuses[2].json() == {"detail": "Too many requests"}
        assert 1 <= int(statuses[2].headers["Retry-After"]) <= 60

    async def test_exhausting_one_caller_does_not_affect_another(self) -> None:
        async with _client(_app(rate_limit_create_per_window=1)) as client:
            await client.post("/payments/intents", json=_body(), headers=_create_headers(SHOP))
            shop = await client.post(
                "/payments/intents", json=_body(), headers=_create_headers(SHOP)
            )
            admin = await client.post(
                "/payments/intents", json=_body(), headers=_create_headers(ADMIN)
            )

        assert (shop.status_code, admin.status_code) == (429, 201)

    async def test_each_route_has_its_own_budget(self) -> None:
        application = _app(rate_limit_create_per_window=1, rate_limit_read_per_window=2)
        async with _client(application) as client:
            await client.post("/payments/intents", json=_body(), headers=_create_headers(SHOP))
            created_again = await client.post(
                "/payments/intents", json=_body(), headers=_create_headers(SHOP)
            )
            reads = [
                await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)
                for _ in range(3)
            ]
            by_order = await client.get("/payments/intents?order_reference=X", headers=SHOP)

        assert created_again.status_code == 429
        assert [r.status_code for r in reads] == [404, 404, 429]
        assert by_order.status_code == 429  # les deux lectures partagent le budget `intents.read`

    async def test_two_instances_on_the_same_database_share_the_budget(self) -> None:
        engine = _engine()
        first, second = (_app(engine, rate_limit_create_per_window=2) for _ in range(2))
        async with _client(first) as a, _client(second) as b:
            one = await a.post("/payments/intents", json=_body(), headers=_create_headers(SHOP))
            two = await b.post("/payments/intents", json=_body(), headers=_create_headers(SHOP))
            three = await a.post("/payments/intents", json=_body(), headers=_create_headers(SHOP))

        assert (one.status_code, two.status_code, three.status_code) == (201, 201, 429)

    async def test_unauthenticated_requests_never_consume_a_budget(self) -> None:
        async with _client(_app(rate_limit_read_per_window=1)) as client:
            for _ in range(5):
                denied = await client.get(
                    f"/payments/intents/{uuid.uuid4()}", headers={"Authorization": "Bearer nope"}
                )
                assert denied.status_code == 401
            allowed = await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)

        assert allowed.status_code == 404

    async def test_health_is_not_rate_limited(self) -> None:
        async with _client(_app(rate_limit_read_per_window=1)) as client:
            responses = [await client.get("/health") for _ in range(5)]

        assert {r.status_code for r in responses} == {200}


class TestHealthUnderLoad:
    async def test_health_stays_200_and_fast_under_200_parallel_requests(self) -> None:
        application = _app(max_concurrent_requests=8)
        durations: list[float] = []

        async def probe(client: AsyncClient) -> int:
            started = time.perf_counter()
            response = await client.get("/health")
            durations.append(time.perf_counter() - started)
            return response.status_code

        async def attack(client: AsyncClient) -> int:
            response = await client.post(
                "/payments/intents",
                content=b"{" * 2000,
                headers={"Authorization": "Bearer wrong", "Idempotency-Key": "attack-key-1"},
            )
            return response.status_code

        async with _client(application) as client:
            results = await asyncio.gather(
                *[probe(client) for _ in range(200)], *[attack(client) for _ in range(200)]
            )

        assert results[:200] == [200] * 200
        assert set(results[200:]) <= {401, 413, 503}
        durations.sort()
        assert durations[int(len(durations) * 0.95)] < 0.2


class TestSanitizedErrors:
    @staticmethod
    def _with_failing_lookup(error: Exception) -> FastAPI:
        application = _app()

        class Failing:
            def execute(self, _: str) -> None:
                raise error

        services = application.state.intent_services
        application.state.intent_services = dataclasses.replace(services, get_by_id=Failing())
        return application

    async def _get(self, application: FastAPI) -> Any:
        async with _client(application) as client:
            return await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)

    async def test_database_failure_is_a_generic_503(self) -> None:
        error = OperationalError(
            "SELECT secret_column FROM payment_intents WHERE id = %(id)s",
            {"id": "x"},
            Exception("connection to server at 10.0.0.5 port 5432 failed: /var/run/pg.sock"),
        )

        response = await self._get(self._with_failing_lookup(error))

        assert response.status_code == 503
        assert response.json() == {"detail": "Service unavailable"}
        assert response.headers["Retry-After"] == "1"
        for leak in ("SELECT", "secret_column", "10.0.0.5", "pg.sock", "Traceback"):
            assert leak not in response.text

    async def test_exhausted_connection_pool_is_a_generic_503(self) -> None:
        error = PoolTimeoutError("QueuePool limit of size 5 overflow 5 reached")

        response = await self._get(self._with_failing_lookup(error))

        assert response.status_code == 503
        assert response.json() == {"detail": "Service unavailable"}

    async def test_unexpected_error_is_a_generic_500_without_path_or_stack(self) -> None:
        response = await self._get(
            self._with_failing_lookup(RuntimeError("/app/app/secret/module.py exploded"))
        )

        assert response.status_code == 500
        assert response.json() == {"detail": "Erreur interne."}
        for leak in ("/app/", "module.py", "exploded", "Traceback", "File "):
            assert leak not in response.text

    async def test_unknown_route_and_wrong_method_stay_terse(self) -> None:
        async with _client(_app()) as client:
            missing = await client.get("/nope")
            wrong_method = await client.delete("/payments/intents", headers=SHOP)

        assert missing.json() == {"detail": "Not Found"}
        assert wrong_method.status_code == 405
        assert wrong_method.json() == {"detail": "Method Not Allowed"}

    async def test_validation_error_does_not_echo_card_data(self) -> None:
        body = {**_body(), "card_number": CARD}
        async with _client(_app()) as client:
            response = await client.post(
                "/payments/intents", json=body, headers=_create_headers(SHOP)
            )

        assert response.status_code == 422
        assert CARD not in response.text


SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"


def _app_with_logs(stream: io.StringIO, **overrides: Any) -> FastAPI:
    settings = Settings(**overrides)
    events = StructlogBusinessEventLogger(settings.service_name, stream)
    return create_app(settings, _engine(), events)


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for record in records:
        jsonschema.validate(record, schema)  # un événement par ligne, au schéma commun
    return records


class TestLogsNeverLeakSecrets:
    async def test_captured_logs_follow_the_schema_and_contain_no_token_card_or_secret(
        self,
    ) -> None:
        stream = io.StringIO()
        failing_token = "wrong-token-should-not-be-logged"
        application = _app_with_logs(stream, rate_limit_read_per_window=1)

        class Exploding:
            def execute(self, _: str) -> None:
                raise RuntimeError(f"échec carte {CARD} jeton {TOKEN}")

        application.state.intent_services = dataclasses.replace(
            application.state.intent_services, get_by_id=Exploding()
        )
        async with _client(application) as client:
            await client.post(
                "/payments/intents",
                json={**_body(), "card_number": CARD, "cvv": "123"},
                headers=_create_headers(SHOP),
            )
            await client.get(
                "/payments/intents/x", headers={"Authorization": f"Bearer {failing_token}"}
            )
            await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)  # 500
            await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)  # 429

        output = stream.getvalue()
        by_name = {r["event"]: r for r in _lines(stream)}
        assert {
            "service.request_rejected",
            "payment.service_authenticated",
            "service.unhandled_error",
            names.RATE_LIMITED,
        } <= set(by_name)
        assert by_name[names.RATE_LIMITED]["outcome"] == "denied"
        assert by_name[names.RATE_LIMITED]["reason"] == "rate_limit_exceeded"
        assert by_name[names.RATE_LIMITED]["actor_id"] == "shop"
        for secret in (TOKEN, OTHER_TOKEN, failing_token, CARD, "4242", "cvv"):
            assert secret not in output


class TestGuardEventsAreLogged:
    async def test_413_and_429_are_logged_with_the_request_correlation_id(self) -> None:
        stream = io.StringIO()
        application = _app_with_logs(stream, max_body_bytes=1024, rate_limit_create_per_window=1)
        correlation = "corr-0123456789"
        headers = {**_create_headers(SHOP), "X-Correlation-ID": correlation}
        async with _client(application) as client:
            await client.post("/payments/intents", content=b"x" * 4096, headers=headers)
            await client.post("/payments/intents", json=_body(), headers=headers)
            limited = await client.post("/payments/intents", json=_body(), headers=headers)

        records = {r["event"]: r for r in _lines(stream)}
        assert records[names.PAYLOAD_TOO_LARGE]["reason"] == "payload_too_large"
        assert records[names.RATE_LIMITED]["outcome"] == "denied"
        assert {
            records[n]["correlation_id"] for n in (names.PAYLOAD_TOO_LARGE, names.RATE_LIMITED)
        } == {correlation}
        assert limited.headers["X-Correlation-ID"] == correlation

    async def test_database_outage_is_logged_as_an_error_event(self) -> None:
        stream = io.StringIO()
        application = _app_with_logs(stream)

        class Down:
            def execute(self, _: str) -> None:
                raise OperationalError("SELECT 1", {}, Exception("host 10.0.0.5"))

        application.state.intent_services = dataclasses.replace(
            application.state.intent_services, get_by_id=Down()
        )
        async with _client(application) as client:
            await client.get(f"/payments/intents/{uuid.uuid4()}", headers=SHOP)

        record = next(r for r in _lines(stream) if r["event"] == names.DATABASE_UNAVAILABLE)
        assert (record["outcome"], record["reason"]) == ("error", "database_unavailable")
        assert "10.0.0.5" not in stream.getvalue() and "SELECT" not in stream.getvalue()
