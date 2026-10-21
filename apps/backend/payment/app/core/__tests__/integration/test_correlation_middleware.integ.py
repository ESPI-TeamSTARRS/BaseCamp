import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_unhandled_error_handler
from app.core.events.business_event import BusinessEvent
from app.core.logging import correlation
from app.core.logging.correlation_id_middleware import CorrelationIdMiddleware

VALID_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[BusinessEvent, str]] = []

    def log(self, event: BusinessEvent) -> None:
        self.events.append((event, correlation.current_correlation_id()))


def _app(events: CapturingLogger) -> FastAPI:
    application = FastAPI()
    application.add_middleware(CorrelationIdMiddleware)
    register_unhandled_error_handler(application, events)

    @application.get("/echo")
    def echo() -> dict[str, str]:
        return {"correlation_id": correlation.current_correlation_id()}

    @application.get("/boom")
    def boom() -> None:
        raise RuntimeError("detail interne secret: postgres://u:p@h/db")

    return application


async def _get(application: FastAPI, path: str, headers: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path, headers=headers)


class TestCorrelationMiddleware:
    async def test_a_valid_incoming_id_is_used_and_echoed(self) -> None:
        response = await _get(_app(CapturingLogger()), "/echo", {"X-Correlation-ID": VALID_ID})

        assert response.headers["X-Correlation-ID"] == VALID_ID
        assert response.json() == {"correlation_id": VALID_ID}

    @pytest.mark.parametrize("incoming", [None, "court", "avec espace dedans", "x" * 100])
    async def test_a_missing_or_invalid_id_is_replaced_by_a_generated_one(
        self, incoming: str | None
    ) -> None:
        headers = {"X-Correlation-ID": incoming} if incoming else None

        response = await _get(_app(CapturingLogger()), "/echo", headers)

        generated = response.headers["X-Correlation-ID"]
        assert correlation.is_valid_correlation_id(generated)
        assert generated != incoming
        assert response.json() == {"correlation_id": generated}


class TestUnhandledError:
    async def test_emits_an_error_event_and_returns_a_generic_500(self) -> None:
        events = CapturingLogger()

        response = await _get(_app(events), "/boom", {"X-Correlation-ID": VALID_ID})

        assert response.status_code == 500
        assert response.json() == {"detail": "Erreur interne."}
        assert response.headers["X-Correlation-ID"] == VALID_ID
        assert len(events.events) == 1
        event, correlation_id = events.events[0]
        assert (event.event, event.outcome.value, event.reason) == (
            "service.unhandled_error",
            "error",
            "internal_error",
        )
        assert correlation_id == VALID_ID
        assert "postgres" not in json.dumps(event.__dict__, default=str)


class TestNonHttpScope:
    async def test_a_lifespan_scope_is_passed_through_untouched(self) -> None:
        seen: list[str] = []

        async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
            seen.append(scope["type"])

        await CorrelationIdMiddleware(inner)({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

        assert seen == ["lifespan"]
