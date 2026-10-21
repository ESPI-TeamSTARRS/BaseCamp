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
from app.password_reset.__tests__.fakes import FakeResetMailer
from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.password_reset.application.reset_password import ResetPasswordUseCase
from app.password_reset.infrastructure.repositories.sqlalchemy_password_reset_unit_of_work import (
    SqlAlchemyPasswordResetUnitOfWork,
)
from app.registration.__tests__.fakes import FakeClock, FakeEmailFingerprinter, FakePasswordHasher
from app.registration.domain.entities.user import User
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

SCHEMA = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
PHRASE = "aaaa-bbbb-aaaa-bbbb"
EMAIL = "camille.dupont@example.com"
CORRELATION = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class Stack:
    def __init__(self, mail_fails: bool = False) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        AuthBase.metadata.create_all(self.engine)
        self.stream = io.StringIO()
        self.mailer = FakeResetMailer(fail=mail_fails)
        events = StructlogBusinessEventLogger("basecamp-auth", self.stream)
        clock = FakeClock()
        tokens = SecureTokenGenerator()
        user = User.register(EmailAddress.of(EMAIL), "old-hash", clock.now())
        with SqlAlchemyUnitOfWork(self.engine) as work:
            work.users.add(user)
            work.commit()
        self.application = create_app()
        self.application.state.request_password_reset_use_case = RequestPasswordResetUseCase(
            lambda: SqlAlchemyPasswordResetUnitOfWork(self.engine),
            tokens,
            self.mailer,
            clock,
            events,
            FakeEmailFingerprinter(),
        )
        self.application.state.reset_password_use_case = ResetPasswordUseCase(
            lambda: SqlAlchemyPasswordResetUnitOfWork(self.engine),
            PasswordPolicy(FileCommonPasswordList()),
            FakePasswordHasher(),
            tokens,
            self.mailer,
            clock,
            events,
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


def check_lines(stack: Stack) -> list[dict[str, Any]]:
    lines = stack.lines()
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    for line in lines:
        validator.validate(line)
        assert line["service"] == "basecamp-auth"
        assert line["correlation_id"] == CORRELATION
    return lines


class TestPasswordResetJsonLines:
    async def test_the_whole_flow_writes_schema_valid_lines_without_secrets(
        self, stack: Stack
    ) -> None:
        await call(stack, "/password/forgot", {"email": EMAIL})
        token = stack.mailer.links[-1][1]
        await call(stack, "/password/forgot", {"email": "inconnu@example.com"})
        await call(stack, "/password/reset", {"token": token, "password": "court"})
        await call(stack, "/password/reset", {"token": token, "password": PHRASE})
        await call(stack, "/password/reset", {"token": token, "password": PHRASE})

        lines = check_lines(stack)
        assert [(line["event"], line["outcome"], line.get("reason")) for line in lines] == [
            ("auth.password_reset_requested", "success", None),
            ("auth.password_reset_rejected", "denied", "unknown_account"),
            ("auth.password_reset_rejected", "denied", "weak_password"),
            ("auth.password_reset_completed", "success", None),
            ("auth.password_reset_rejected", "denied", "invalid_or_expired_token"),
        ]
        raw = stack.stream.getvalue()
        for secret in (PHRASE, token, "camille", "dupont", "inconnu", "court"):
            assert secret not in raw

    async def test_a_mail_outage_is_logged_with_the_request_correlation_id(self) -> None:
        stack = Stack(mail_fails=True)
        try:
            await call(stack, "/password/forgot", {"email": EMAIL})

            lines = check_lines(stack)
            assert [(line["event"], line.get("reason")) for line in lines] == [
                ("auth.password_reset_requested", None),
                ("auth.email_delivery_failed", "mail_delivery_failed"),
            ]
            assert lines[-1]["attributes"] == {"kind": "password_reset"}
        finally:
            stack.engine.dispose()
