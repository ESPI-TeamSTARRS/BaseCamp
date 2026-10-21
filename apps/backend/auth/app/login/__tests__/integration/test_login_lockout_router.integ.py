from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL, LoginStack

GENERIC = {"detail": "Identifiants invalides."}


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


async def login(
    client: AsyncClient, email: str = EMAIL, password: str = ACCOUNT_SECRET
) -> Response:
    return await client.post("/login", json={"email": email, "password": password})


def shape(response: Response) -> tuple[int, dict[str, str], object]:
    headers = {k: v for k, v in response.headers.items() if k != "x-correlation-id"}
    return response.status_code, headers, response.json()


class TestBruteForce:
    async def test_five_failures_lock_the_account_and_the_right_password_gets_the_same_401(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        failures = [await login(client, password="mauvais") for _ in range(5)]

        locked = await login(client)

        assert locked.status_code == 401
        assert locked.json() == GENERIC
        assert shape(locked) == shape(failures[0])
        assert "set-cookie" not in locked.headers
        assert "retry-after" not in locked.headers
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0

    async def test_known_and_unknown_addresses_behave_identically(
        self, client: AsyncClient
    ) -> None:
        for _ in range(5):
            await login(client, password="mauvais")
            await login(client, email="inconnu@example.com", password="mauvais")

        known = await login(client)
        unknown = await login(client, email="inconnu@example.com")

        assert shape(known) == shape(unknown)

    async def test_the_lock_is_stored_in_the_database(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        for _ in range(5):
            await login(client, password="mauvais")

        assert (
            stack.scalar("SELECT COUNT(*) FROM login_lockouts WHERE locked_until IS NOT NULL") == 1
        )
        assert stack.scalar("SELECT scope FROM login_lockouts") == "password"

    async def test_the_account_works_again_after_the_lock_and_a_success_clears_the_row(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        for _ in range(5):
            await login(client, password="mauvais")
        stack.clock.current += timedelta(minutes=16)

        response = await login(client)

        assert response.status_code == 200
        assert stack.scalar("SELECT COUNT(*) FROM login_lockouts") == 0

    async def test_another_account_is_not_affected(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account("autre@example.com")
        for _ in range(5):
            await login(client, password="mauvais")

        assert (await login(client, email="autre@example.com")).status_code == 200

    async def test_a_relapse_locks_longer_up_to_the_cap(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        waits = []
        for _ in range(4):
            for _ in range(5):
                await login(client, password="mauvais")
            waits.append(stack.scalar("SELECT level FROM login_lockouts"))
            stack.clock.current += timedelta(minutes=61)

        assert waits == [1, 2, 3, 4]
        assert (await login(client)).status_code == 200
