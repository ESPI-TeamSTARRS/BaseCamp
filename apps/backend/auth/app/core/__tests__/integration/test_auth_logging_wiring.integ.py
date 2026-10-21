import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class TestAuthLoggingWiring:
    async def test_the_service_echoes_a_valid_correlation_id(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://t"
        ) as client:
            response = await client.get("/health", headers={"X-Correlation-ID": CORRELATION_ID})

        assert response.headers["X-Correlation-ID"] == CORRELATION_ID

    async def test_a_generated_id_is_returned_without_the_header(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://t"
        ) as client:
            response = await client.get("/health")

        assert len(response.headers["X-Correlation-ID"]) >= 8

    async def test_an_unexpected_error_writes_a_sanitized_error_event(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        application = create_app()

        @application.get("/boom")
        def boom() -> None:
            raise RuntimeError("postgres://u:secret@h/db")

        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            response = await client.get("/boom", headers={"X-Correlation-ID": CORRELATION_ID})

        record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert response.status_code == 500
        assert (record["service"], record["event"], record["outcome"], record["reason"]) == (
            "basecamp-auth",
            "service.unhandled_error",
            "error",
            "internal_error",
        )
        assert record["correlation_id"] == CORRELATION_ID
        assert "secret" not in json.dumps(record)
