from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app
from app.password_reset.__tests__.fakes import (
    FakeResetMailer,
    add_refresh_token,
    create_refresh_tokens,
)
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

EMAIL = "camille@example.com"
NEW_PASSWORD = "aaaa-bbbb-aaaa-bbbb"
GENERIC = {
    "message": "Si un compte existe pour cette adresse, un email de réinitialisation vient d'être envoyé."
}


class Stack:
    """Application reelle sur SQLite en memoire et un faux serveur de messagerie."""

    def __init__(self, mail_fails: bool = False) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        AuthBase.metadata.create_all(self.engine)
        create_refresh_tokens(self.engine)
        self.mailer = FakeResetMailer(fail=mail_fails)
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        tokens = SecureTokenGenerator()
        self.application = create_app()
        self.application.state.request_password_reset_use_case = RequestPasswordResetUseCase(
            lambda: SqlAlchemyPasswordResetUnitOfWork(self.engine),
            tokens,
            self.mailer,
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
        )
        self.application.state.reset_password_use_case = ResetPasswordUseCase(
            lambda: SqlAlchemyPasswordResetUnitOfWork(self.engine),
            PasswordPolicy(FileCommonPasswordList()),
            FakePasswordHasher(),
            tokens,
            self.mailer,
            self.clock,
            self.events,
        )

    def add_user(self, email: str = EMAIL) -> None:
        user = User.register(EmailAddress.of(email), "old-hash", self.clock.now())
        with SqlAlchemyUnitOfWork(self.engine) as work:
            work.users.add(user)
            work.commit()
        add_refresh_token(self.engine, user.id, f"{email}-1")
        add_refresh_token(self.engine, user.id, f"{email}-2")

    def scalar(self, sql: str) -> Any:
        with self.engine.connect() as connection:
            return connection.execute(text(sql)).scalar_one()


@pytest.fixture
def make_stack() -> Iterator[Callable[..., Stack]]:
    created: list[Stack] = []

    def factory(**options: bool) -> Stack:
        created.append(Stack(**options))
        return created[-1]

    yield factory
    for stack in created:
        stack.engine.dispose()


@pytest.fixture
async def client_and_stack(
    make_stack: Callable[..., Stack],
) -> AsyncIterator[tuple[AsyncClient, Stack]]:
    stack = make_stack()
    stack.add_user()
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as client:
        yield client, stack


async def forgot(client: AsyncClient, email: str = EMAIL) -> Any:
    return await client.post("/password/forgot", json={"email": email})


def last_token(stack: Stack) -> str:
    return stack.mailer.links[-1][1]


class TestForgot:
    async def test_known_and_unknown_addresses_get_the_exact_same_response(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack

        known = await forgot(client)
        unknown = await forgot(client, "inconnu@example.com")
        invalid = await forgot(client, "pas-un-email")

        assert known.status_code == 202
        assert known.json() == GENERIC
        for other in (unknown, invalid):
            assert (other.status_code, other.content) == (known.status_code, known.content)
            assert other.headers["content-type"] == known.headers["content-type"]
        assert [to for to, _ in stack.mailer.links] == [EMAIL]

    async def test_only_the_hash_of_the_token_is_stored(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack

        await forgot(client)

        stored = stack.scalar("SELECT token_hash FROM password_reset_tokens")
        assert stored != last_token(stack)
        assert len(stored) == 64

    async def test_a_mail_outage_changes_nothing_for_the_caller_and_is_logged(
        self, make_stack: Callable[..., Stack]
    ) -> None:
        stack = make_stack(mail_fails=True)
        stack.add_user()
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            response = await forgot(client)

        assert (response.status_code, response.json()) == (202, GENERIC)
        assert [e.event for e in stack.events.events] == [
            "auth.password_reset_requested",
            "auth.email_delivery_failed",
        ]

    async def test_the_per_address_limit_keeps_the_same_response(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack

        responses = [await forgot(client) for _ in range(5)]

        assert {(r.status_code, r.content) for r in responses} == {(202, responses[0].content)}
        assert len(stack.mailer.links) == 3
        assert stack.events.events[-1].reason == "rate_limited"

    async def test_the_limit_window_expires(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        for _ in range(4):
            await forgot(client)
        stack.clock.current += timedelta(hours=1, seconds=1)

        await forgot(client)

        assert len(stack.mailer.links) == 4

    async def test_unknown_field_and_bad_shape_are_sanitized_422(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, _ = client_and_stack

        extra = await client.post("/password/forgot", json={"email": EMAIL, "role": "operator"})
        missing = await client.post("/password/forgot", json={})

        for response in (extra, missing):
            assert response.status_code == 422
            assert "operator" not in response.text
            assert "Traceback" not in response.text


class TestReset:
    async def test_a_valid_token_replaces_the_password_and_notifies(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await forgot(client)

        response = await client.post(
            "/password/reset", json={"token": last_token(stack), "password": NEW_PASSWORD}
        )

        assert response.status_code == 200
        assert stack.scalar("SELECT password_hash FROM users").startswith("hashed::")
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0
        assert stack.mailer.changes == [EMAIL]

    async def test_the_link_cannot_be_used_twice(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await forgot(client)
        body = {"token": last_token(stack), "password": NEW_PASSWORD}
        await client.post("/password/reset", json=body)

        replay = await client.post("/password/reset", json=body)

        assert replay.status_code == 400
        assert replay.json() == {"detail": "Lien de réinitialisation invalide ou expiré."}

    async def test_unknown_expired_and_replaced_tokens_share_one_error(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await forgot(client)
        first = last_token(stack)
        await forgot(client)  # invalide `first`
        second = last_token(stack)
        stack.clock.current += timedelta(minutes=31)

        bodies = []
        for token in ("x" * 43, first, second):
            response = await client.post(
                "/password/reset", json={"token": token, "password": NEW_PASSWORD}
            )
            assert response.status_code == 400
            bodies.append(response.content)

        assert len(set(bodies)) == 1

    @pytest.mark.parametrize("password", ["court", "Password1234", "a" * 129])
    async def test_a_weak_password_is_a_sanitized_422_and_keeps_the_link_valid(
        self, client_and_stack: tuple[AsyncClient, Stack], password: str
    ) -> None:
        client, stack = client_and_stack
        await forgot(client)
        token = last_token(stack)

        response = await client.post("/password/reset", json={"token": token, "password": password})

        assert response.status_code == 422
        assert response.json()["fields"] == ["password"]
        assert password not in response.text
        assert token not in response.text
        ok = await client.post("/password/reset", json={"token": token, "password": NEW_PASSWORD})
        assert ok.status_code == 200

    async def test_unknown_field_is_refused_without_being_reflected(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, _ = client_and_stack

        response = await client.post(
            "/password/reset", json={"token": "t", "password": NEW_PASSWORD, "role": "operator"}
        )

        assert response.status_code == 422
        assert "operator" not in response.text
