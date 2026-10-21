from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL, LoginStack

CSRF = {"X-Requested-With": "basecamp"}
GENERIC_BODY = {"detail": "Session expirée."}


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[LoginStack]:
    stack = LoginStack(events)
    stack.add_account()
    yield stack
    stack.engine.dispose()


@pytest.fixture
async def client(stack: LoginStack) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as http:
        yield http


def cookie_value(response: Response) -> str:
    return response.headers["set-cookie"].split(";")[0].split("=", 1)[1]


async def login(client: AsyncClient, stack: LoginStack) -> str:
    response = await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
    assert response.status_code == 200
    return cookie_value(response)


async def refresh(
    client: AsyncClient, token: str | None, headers: dict[str, str] | None = CSRF
) -> Response:
    cookies = {"Cookie": f"refresh_token={token}"} if token is not None else {}
    return await client.post("/refresh", headers={**(headers or {}), **cookies})


async def logout(
    client: AsyncClient, token: str | None, headers: dict[str, str] | None = CSRF
) -> Response:
    cookies = {"Cookie": f"refresh_token={token}"} if token is not None else {}
    return await client.post("/logout", headers={**(headers or {}), **cookies})


class TestRefresh:
    async def test_it_issues_a_new_access_token_and_a_new_refresh_cookie(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        old = await login(client, stack)

        response = await refresh(client, old)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type", "expires_in"}
        assert (body["token_type"], body["expires_in"]) == ("Bearer", 900)
        claims = jwt.decode(body["access_token"], options={"verify_signature": False})
        assert claims["exp"] - claims["iat"] == 900
        new = cookie_value(response)
        assert new != old
        assert response.headers["cache-control"] == "no-store"
        attributes = {p.strip().lower() for p in response.headers["set-cookie"].split(";")}
        assert {"httponly", "secure", "samesite=strict", "path=/api/auth", "max-age=604800"} <= (
            attributes
        )

    async def test_the_new_access_token_opens_me(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        response = await refresh(client, await login(client, stack))

        profile = await client.get(
            "/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
        )

        assert profile.status_code == 200
        assert profile.json()["email"] == EMAIL

    async def test_the_old_token_is_invalidated_and_the_chain_continues(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        old = await login(client, stack)
        first = cookie_value(await refresh(client, old))

        second = await refresh(client, first)

        assert second.status_code == 200
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens WHERE used_at IS NULL") == 1
        assert stack.scalar("SELECT COUNT(DISTINCT family_id) FROM refresh_tokens") == 1

    async def test_only_hashes_are_stored(self, client: AsyncClient, stack: LoginStack) -> None:
        token = await login(client, stack)
        new = cookie_value(await refresh(client, token))

        stored = set(stack.column("SELECT token_hash FROM refresh_tokens"))
        assert not {token, new} & stored

    async def test_the_csrf_header_is_mandatory(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        token = await login(client, stack)

        response = await refresh(client, token, headers=None)

        assert response.status_code == 403
        assert response.json() == {"detail": "Requête refusée."}
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens WHERE used_at IS NULL") == 1

    async def test_a_replayed_token_revokes_the_family_and_is_logged(
        self, client: AsyncClient, stack: LoginStack, events: InMemoryBusinessEventLogger
    ) -> None:
        old = await login(client, stack)
        new = cookie_value(await refresh(client, old))
        events.events.clear()

        replay = await refresh(client, old)

        assert replay.status_code == 401
        assert replay.json() == GENERIC_BODY
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0
        assert (await refresh(client, new)).status_code == 401
        assert next(e.event for e in events.events) == "auth.refresh_reuse_detected"

    async def test_every_failure_is_the_same_401_and_clears_the_cookie(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        old = await login(client, stack)
        await refresh(client, old)
        stack.clock.current += timedelta(days=8)
        failures = [
            await refresh(client, None),
            await refresh(client, "never-issued"),
            await refresh(client, old),
        ]

        for response in failures:
            assert response.status_code == 401
            assert response.json() == GENERIC_BODY
            cleared = response.headers["set-cookie"].lower()
            assert cleared.startswith('refresh_token="";') or "max-age=0" in cleared
            assert "path=/api/auth" in cleared

    async def test_an_expired_token_is_refused(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        token = await login(client, stack)
        stack.clock.current += timedelta(days=7)

        response = await refresh(client, token)

        assert response.status_code == 401
        assert response.json() == GENERIC_BODY

    async def test_a_disabled_account_cannot_refresh(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        token = await login(client, stack)
        with stack.engine.begin() as connection:
            connection.execute(text("UPDATE users SET disabled_at = '2026-01-01 12:00:00'"))

        response = await refresh(client, token)

        assert response.status_code == 401
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0


class TestLogout:
    async def test_it_revokes_the_session_and_clears_the_cookie(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        token = await login(client, stack)

        response = await logout(client, token)

        assert response.status_code == 204
        assert response.content == b""
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0
        assert (await refresh(client, token)).status_code == 401

    async def test_it_is_idempotent(self, client: AsyncClient, stack: LoginStack) -> None:
        token = await login(client, stack)
        await logout(client, token)

        again = await logout(client, token)
        without_cookie = await logout(client, None)

        assert (again.status_code, without_cookie.status_code) == (204, 204)

    async def test_it_works_with_an_already_rotated_token(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        old = await login(client, stack)
        await refresh(client, old)

        response = await logout(client, old)

        assert response.status_code == 204
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0

    async def test_the_csrf_header_is_mandatory(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        token = await login(client, stack)

        response = await logout(client, token, headers=None)

        assert response.status_code == 403
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 1

    async def test_the_access_token_already_issued_expires_by_itself(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        response = await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
        access = response.json()["access_token"]
        await logout(client, cookie_value(response))

        profile = await client.get("/me", headers={"Authorization": f"Bearer {access}"})

        assert profile.status_code == 200
