"""Lignes JSON reellement ecrites par la connexion : contrat commun et absence de secret."""

import base64
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL, LoginStack

SCHEMA = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class Harness:
    def __init__(self) -> None:
        self.stream = io.StringIO()
        self.stack = LoginStack(StructlogBusinessEventLogger("basecamp-auth", self.stream))

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line.strip()]


@pytest.fixture
def harness() -> Iterator[Harness]:
    value = Harness()
    yield value
    value.stack.engine.dispose()


class TestLoginJsonLines:
    async def test_the_flow_writes_schema_valid_lines_without_secrets(
        self, harness: Harness
    ) -> None:
        harness.stack.add_account()
        headers = {"X-Correlation-ID": CORRELATION, "X-Forwarded-For": "203.0.113.7"}
        async with AsyncClient(
            transport=ASGITransport(app=harness.stack.application), base_url="http://t"
        ) as client:
            ok = await client.post(
                "/login", json={"email": EMAIL, "password": ACCOUNT_SECRET}, headers=headers
            )
            await client.post(
                "/login", json={"email": EMAIL, "password": "mauvais-mot-de-passe"}, headers=headers
            )
            await client.post(
                "/login",
                json={"email": "inconnu@example.com", "password": ACCOUNT_SECRET},
                headers=headers,
            )
            await client.get("/me", headers={**headers, "Authorization": "Bearer pas.un.jeton"})
            token = ok.json()["access_token"]
            refresh = ok.headers["set-cookie"].split(";")[0].split("=", 1)[1]

        lines = harness.lines()
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        for line in lines:
            validator.validate(line)
            assert line["service"] == "basecamp-auth"
            assert line["correlation_id"] == CORRELATION
        assert [(line["event"], line["outcome"], line.get("reason")) for line in lines] == [
            ("auth.login_succeeded", "success", None),
            ("auth.login_failed", "denied", "invalid_credentials"),
            ("auth.login_failed", "denied", "invalid_credentials"),
            ("auth.token_rejected", "denied", "invalid"),
        ]
        assert [line.get("attributes", {}).get("cause") for line in lines[1:3]] == [
            "wrong_password",
            "unknown_account",
        ]
        assert lines[1]["client_ip"] == "203.0.113.7"
        self._assert_no_secret(harness, token, refresh)

    @staticmethod
    def _assert_no_secret(harness: Harness, token: str, refresh: str) -> None:
        raw = harness.stream.getvalue()
        private = harness.stack.keys.signing_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        private_raw = base64.urlsafe_b64encode(
            harness.stack.keys.signing_key.private_bytes_raw()
        ).decode()
        for secret in (
            ACCOUNT_SECRET,
            "mauvais-mot-de-passe",
            token,
            refresh,
            "camille",
            "inconnu",
        ):
            assert secret not in raw
        assert private.splitlines()[1] not in raw
        assert private_raw.rstrip("=") not in raw
