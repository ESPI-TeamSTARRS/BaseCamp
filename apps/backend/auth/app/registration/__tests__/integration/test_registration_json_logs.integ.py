"""Lignes JSON reellement ecrites (adaptateur structlog) : contrat commun et absence de secret."""

import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.registration.__tests__.fakes import (
    FakeClock,
    FakeEmailFingerprinter,
    FakeMailer,
    FakePasswordHasher,
)
from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.application.verify_email import VerifyEmailUseCase
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

SCHEMA = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
PHRASE = "sentier-du-mont-blanc"
EMAIL = "camille.dupont@example.com"
CORRELATION = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class Stack:
    def __init__(self) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        AuthBase.metadata.create_all(self.engine)
        self.stream = io.StringIO()
        self.mailer = FakeMailer()
        events = StructlogBusinessEventLogger("basecamp-auth", self.stream)
        clock = FakeClock()
        tokens = SecureTokenGenerator()
        self.application = create_app()
        self.application.state.register_account_use_case = RegisterAccountUseCase(
            lambda: SqlAlchemyUnitOfWork(self.engine),
            PasswordPolicy(FileCommonPasswordList()),
            FakePasswordHasher(),
            tokens,
            self.mailer,
            clock,
            events,
            FakeEmailFingerprinter(),
        )
        self.application.state.verify_email_use_case = VerifyEmailUseCase(
            lambda: SqlAlchemyUnitOfWork(self.engine), tokens, clock, events
        )

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines() if line.strip()]


@pytest.fixture
def stack() -> Iterator[Stack]:
    value = Stack()
    yield value
    value.engine.dispose()


async def call(stack: Stack, path: str, body: dict[str, str]) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://t"
    ) as client:
        await client.post(path, json=body, headers={"X-Correlation-ID": CORRELATION})


class TestRegistrationJsonLines:
    async def test_the_whole_flow_writes_schema_valid_lines_without_secrets(
        self, stack: Stack
    ) -> None:
        await call(stack, "/register", {"email": EMAIL, "password": PHRASE})
        token = stack.mailer.verifications[-1][1]
        await call(stack, "/register", {"email": EMAIL, "password": PHRASE})
        await call(stack, "/register", {"email": "invalide", "password": "court"})
        await call(stack, "/verify-email", {"token": token})
        await call(stack, "/verify-email", {"token": token})

        lines = stack.lines()
        validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        for line in lines:
            validator.validate(line)
            assert line["service"] == "basecamp-auth"
            assert line["correlation_id"] == CORRELATION
        assert [(line["event"], line["outcome"], line.get("reason")) for line in lines] == [
            ("auth.account_registered", "success", None),
            ("auth.registration_rejected", "denied", "email_already_used"),
            ("auth.registration_rejected", "denied", "invalid_email"),
            ("auth.email_verified", "success", None),
            ("auth.email_verification_failed", "denied", "invalid_or_expired_token"),
        ]
        raw = stack.stream.getvalue()
        for secret in (PHRASE, token, "camille", "dupont", "court"):
            assert secret not in raw
