from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.backoffice.__tests__.fakes import PNG
from app.backoffice.__tests__.stack import BackofficeStack, b64
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger

INVITED = "nouvel.operateur@example.com"
PASSWORD = "sentier-" + uuid4().hex
ACCOUNTS_OF_INVITED = "SELECT COUNT(*) FROM users WHERE email = 'nouvel.operateur@example.com'"
ROLE_OF_INVITED = "SELECT role, disabled_at FROM users WHERE email = 'nouvel.operateur@example.com'"
REFUSED = {"detail": "Invitation invalide ou expirée."}


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[BackofficeStack]:
    stack = BackofficeStack(events)
    yield stack
    stack.engine.dispose()


@pytest.fixture
async def client(stack: BackofficeStack) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as http:
        yield http


class TestCompletion:
    async def test_a_valid_token_creates_the_operator_who_can_then_log_in(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)

        response = await stack.complete(client, token, PASSWORD)

        assert response.status_code == 201
        assert response.json() == {"created": True}
        assert response.headers["cache-control"] == "no-store"
        challenge = str((await stack.identify(client, INVITED)).json()["challenge_id"])
        assert (await stack.face(client, challenge)).status_code == 200
        done = await stack.password(client, challenge, PASSWORD)
        assert done.status_code == 200 and "access_token" in done.json()

    async def test_account_and_template_exist_and_the_token_is_consumed(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)
        await stack.complete(client, token, PASSWORD)

        assert stack.row(ROLE_OF_INVITED) == (
            "operator",
            None,
        )
        assert stack.row("SELECT COUNT(*) FROM operator_face_templates") == (2,)
        assert stack.row("SELECT COUNT(*) FROM operator_invitations WHERE consumed_at IS NULL") == (
            0,
        )

    async def test_only_the_digest_of_the_token_is_in_the_database(
        self, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)

        dump = repr(stack.rows("SELECT * FROM operator_invitations"))

        assert token not in dump

    async def test_the_token_is_single_use(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)
        assert (await stack.complete(client, token, PASSWORD)).status_code == 201

        again = await stack.complete(client, token, PASSWORD)

        assert (again.status_code, again.json()) == (401, REFUSED)

    async def test_two_simultaneous_uses_create_a_single_account(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)

        first = await stack.complete(client, token, PASSWORD)
        second = await stack.complete(client, token, "autre-" + uuid4().hex)

        assert sorted([first.status_code, second.status_code]) == [201, 401]
        assert stack.row(ACCOUNTS_OF_INVITED) == (1,)

    @pytest.mark.parametrize("token", ["inconnu", "a" * 43])
    async def test_an_unknown_token_gets_the_generic_answer(
        self, client: AsyncClient, stack: BackofficeStack, token: str
    ) -> None:
        response = await stack.complete(client, token, PASSWORD)

        assert (response.status_code, response.json()) == (401, REFUSED)

    async def test_an_expired_token_gets_the_same_answer_as_an_unknown_one(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)
        stack.clock.current += timedelta(minutes=5, seconds=1)

        response = await stack.complete(client, token, PASSWORD)

        assert (response.status_code, response.json()) == (401, REFUSED)

    async def test_a_weak_password_is_a_422_and_the_token_is_kept(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)

        weak = await stack.complete(client, token, "court")

        assert weak.status_code == 422
        assert weak.json()["code"] == "password_too_short"
        assert (await stack.complete(client, token, PASSWORD)).status_code == 201

    @pytest.mark.parametrize("count", [0, 2, 11])
    async def test_the_number_of_photos_must_be_three_to_ten(
        self, client: AsyncClient, stack: BackofficeStack, count: int
    ) -> None:
        token = stack.invite(INVITED)

        response = await client.post(
            "/backoffice/invitation/complete",
            json={"token": token, "password": PASSWORD, "images": [b64(PNG)] * count},
        )

        assert response.status_code == 422
        assert stack.row(ACCOUNTS_OF_INVITED) == (0,)

    async def test_a_photo_that_is_not_an_accepted_image_is_a_422_without_account(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)

        response = await stack.complete(client, token, PASSWORD, PNG, PNG, b"GIF89a-x")

        assert response.status_code == 422
        assert stack.row(ACCOUNTS_OF_INVITED) == (0,)
        assert stack.row("SELECT COUNT(*) FROM operator_invitations WHERE consumed_at IS NULL") == (
            1,
        )

    async def test_unknown_fields_and_bad_base64_are_rejected(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)
        base = {"token": token, "password": PASSWORD, "images": [b64(PNG)] * 3}

        extra = await client.post("/backoffice/invitation/complete", json={**base, "role": "admin"})
        garbage = await client.post(
            "/backoffice/invitation/complete", json={**base, "images": ["%%%", "%%%", "%%%"]}
        )

        assert extra.status_code == 422
        assert garbage.status_code == 422
        assert stack.row(ACCOUNTS_OF_INVITED) == (0,)

    async def test_five_bad_tokens_lock_the_address_even_for_the_good_one(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = stack.invite(INVITED)
        for index in range(5):
            assert (await stack.complete(client, f"faux-{index}", PASSWORD)).status_code == 401

        blocked = await stack.complete(client, token, PASSWORD)

        assert (blocked.status_code, blocked.json()) == (401, REFUSED)
        assert stack.row(ACCOUNTS_OF_INVITED) == (0,)

    async def test_nothing_sensitive_reaches_the_logs(
        self,
        client: AsyncClient,
        stack: BackofficeStack,
        events: InMemoryBusinessEventLogger,
    ) -> None:
        token = stack.invite(INVITED)
        await stack.complete(client, "faux", PASSWORD)
        await stack.complete(client, token, PASSWORD)

        text = repr(events.events)

        assert token not in text and PASSWORD not in text and INVITED not in text
        assert b64(PNG) not in text
        assert [e.event for e in events.events if e.event.startswith("auth.operator_invite")] == [
            "auth.operator_invite_created",
            "auth.operator_invite_refused",
            "auth.operator_invite_consumed",
        ]
