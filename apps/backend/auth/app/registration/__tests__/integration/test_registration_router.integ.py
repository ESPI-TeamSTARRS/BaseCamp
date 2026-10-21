from collections.abc import AsyncIterator, Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
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
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

VALID = {"email": "camille@example.com", "password": "sentier-du-mont-blanc"}


class Stack:
    """Application reelle, branchee sur SQLite en memoire et un faux serveur de messagerie."""

    def __init__(self, mail_fails: bool = False, real_hasher: bool = False) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        AuthBase.metadata.create_all(self.engine)
        self.mailer = FakeMailer(fail=mail_fails)
        self.clock = FakeClock()
        self.events = InMemoryBusinessEventLogger()
        tokens = SecureTokenGenerator()
        hasher = Argon2PasswordHasher() if real_hasher else FakePasswordHasher()
        self.application = create_app()
        self.application.state.register_account_use_case = RegisterAccountUseCase(
            lambda: SqlAlchemyUnitOfWork(self.engine),
            PasswordPolicy(FileCommonPasswordList()),
            hasher,
            tokens,
            self.mailer,
            self.clock,
            self.events,
            FakeEmailFingerprinter(),
        )
        self.application.state.verify_email_use_case = VerifyEmailUseCase(
            lambda: SqlAlchemyUnitOfWork(self.engine), tokens, self.clock, self.events
        )

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
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as client:
        yield client, stack


async def register(
    client: AsyncClient, email: str = VALID["email"], phrase: str = VALID["password"]
) -> Response:
    return await client.post("/register", json={"email": email, "password": phrase})


class TestRegister:
    async def test_accepts_a_valid_registration(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack

        response = await register(client)

        assert response.status_code == 202
        assert stack.scalar("SELECT role FROM users") == "customer"
        assert stack.scalar("SELECT email_verified_at IS NULL FROM users") == 1
        assert [to for to, _ in stack.mailer.verifications] == ["camille@example.com"]

    async def test_existing_email_gets_the_exact_same_response(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        first = await register(client)

        second = await register(
            client, email="CAMILLE@example.com ", phrase="un-autre-mot-de-passe"
        )

        assert (second.status_code, second.content) == (first.status_code, first.content)
        assert second.headers["content-type"] == first.headers["content-type"]
        assert stack.scalar("SELECT COUNT(*) FROM users") == 1
        assert stack.mailer.already_exists == ["camille@example.com"]

    @pytest.mark.parametrize(
        ("body", "fields"),
        [
            ({"email": "pas-un-email", "password": "sentier-du-mont-blanc"}, ["email"]),
            ({"email": "camille@example.com", "password": "court"}, ["password"]),
            ({"email": "camille@example.com", "password": "Password1234"}, ["password"]),
            ({"email": "camille@example.com", "password": "a" * 129}, ["password"]),
            ({"email": "nope", "password": "court"}, ["email", "password"]),
        ],
    )
    async def test_invalid_input_is_a_sanitized_422(
        self, client_and_stack: tuple[AsyncClient, Stack], body: dict[str, str], fields: list[str]
    ) -> None:
        client, stack = client_and_stack

        response = await client.post("/register", json=body)

        assert response.status_code == 422
        assert response.json()["fields"] == fields
        for value in body.values():
            assert value not in response.text
        assert stack.scalar("SELECT COUNT(*) FROM users") == 0
        assert stack.mailer.verifications == []

    @pytest.mark.parametrize(
        "payload",
        [
            {**VALID, "role": "operator"},
            {"email": "camille@example.com"},
            {"email": 42, "password": "sentier-du-mont-blanc"},
            {"email": "camille@example.com", "password": ["liste"]},
            {"email": "camille@example.com", "password": "x" * 5000},
            [],
        ],
    )
    async def test_malformed_payloads_are_a_sanitized_422(
        self, client_and_stack: tuple[AsyncClient, Stack], payload: Any
    ) -> None:
        client, _ = client_and_stack

        response = await client.post("/register", json=payload)

        assert response.status_code == 422
        assert response.json()["detail"] == "Requete invalide."
        assert "operator" not in response.text
        assert "input" not in response.json()

    async def test_extra_field_is_not_reflected_nor_named(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, _ = client_and_stack

        response = await client.post("/register", json={**VALID, "is_admin": True})

        assert response.status_code == 422
        assert "is_admin" not in response.text

    async def test_non_json_body_is_a_sanitized_422(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, _ = client_and_stack

        response = await client.post(
            "/register", content=b"{pas du json", headers={"content-type": "application/json"}
        )

        assert response.status_code == 422
        assert "pas du json" not in response.text

    async def test_password_is_stored_as_an_argon2id_hash_only(
        self, make_stack: Callable[..., Stack]
    ) -> None:
        stack = make_stack(real_hasher=True)
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            await register(client)

        stored = stack.scalar("SELECT password_hash FROM users")
        assert stored.startswith("$argon2id$")
        assert VALID["password"] not in stored

    async def test_the_response_stays_identical_when_the_mail_server_is_down(
        self, make_stack: Callable[..., Stack]
    ) -> None:
        stack = make_stack(mail_fails=True)
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            first = await register(client)
            second = await register(client)

        assert (first.status_code, first.content) == (second.status_code, second.content)


class TestVerifyEmail:
    async def test_a_valid_token_verifies_the_email_once(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await register(client)
        token = stack.mailer.verifications[-1][1]

        first = await client.post("/verify-email", json={"token": token})
        second = await client.post("/verify-email", json={"token": token})

        assert first.status_code == 200
        assert stack.scalar("SELECT email_verified_at IS NOT NULL FROM users") == 1
        assert second.status_code == 400

    async def test_only_the_token_hash_is_stored(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await register(client)
        token = stack.mailer.verifications[-1][1]

        stored = stack.scalar("SELECT token_hash FROM email_verification_tokens")

        assert stored != token
        assert len(stored) == 64

    async def test_unknown_expired_and_used_tokens_share_one_generic_error(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, stack = client_and_stack
        await register(client)
        used = stack.mailer.verifications[-1][1]
        await client.post("/verify-email", json={"token": used})
        await register(client, email="autre@example.com", phrase="sentier-du-mont-blanc")
        expired = stack.mailer.verifications[-1][1]
        stack.clock.current += timedelta(hours=24, seconds=1)

        responses = [
            await client.post("/verify-email", json={"token": value})
            for value in ("inconnu-" + "x" * 40, expired, used)
        ]

        assert {(r.status_code, r.content) for r in responses} == {(400, responses[0].content)}
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE email_verified_at IS NULL") == 1

    @pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": "x" * 300}, {"token": 1}])
    async def test_malformed_payloads_are_a_sanitized_422(
        self, client_and_stack: tuple[AsyncClient, Stack], payload: dict[str, Any]
    ) -> None:
        client, _ = client_and_stack

        response = await client.post("/verify-email", json=payload)

        assert response.status_code == 422
        assert "x" * 20 not in response.text

    async def test_extra_field_is_refused(
        self, client_and_stack: tuple[AsyncClient, Stack]
    ) -> None:
        client, _ = client_and_stack

        response = await client.post("/verify-email", json={"token": "abc", "admin": True})

        assert response.status_code == 422


class TestEventsStaySecretFree:
    async def test_no_password_token_or_address_reaches_the_events(
        self, make_stack: Callable[..., Stack]
    ) -> None:
        stack = make_stack(mail_fails=True)
        async with AsyncClient(
            transport=ASGITransport(app=stack.application), base_url="http://test"
        ) as client:
            await register(client)
            await register(client)
            await register(client, email="invalide", phrase="Password1234")
            await client.post("/verify-email", json={"token": "jeton-secret-inconnu"})

        rendered = repr(stack.events.events)
        password_hash = stack.scalar("SELECT password_hash FROM users")
        assert stack.events.events
        for secret in (
            VALID["password"],
            "Password1234",
            "jeton-secret-inconnu",
            "camille",
            password_hash,
        ):
            assert secret not in rendered
