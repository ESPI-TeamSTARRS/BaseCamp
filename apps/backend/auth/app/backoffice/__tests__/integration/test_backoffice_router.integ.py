import json
import statistics
import time
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.backoffice.__tests__.fakes import JPEG, OTHER_PNG, PNG
from app.backoffice.__tests__.stack import OPERATOR_EMAIL, WRONG, BackofficeStack, b64
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL

GENERIC = {"detail": "Identifiants invalides."}


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


def _claims(stack: BackofficeStack, token: str) -> dict[str, object]:
    key = stack.keys.verification_key(jwt.get_unverified_header(token)["kid"])
    assert key is not None
    return dict(
        jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            audience="basecamp-client-api",
            issuer="basecamp-auth",
            options={"verify_exp": False},
        )
    )


class TestIdentify:
    async def test_a_known_operator_gets_a_challenge(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        response = await stack.identify(client)

        assert response.status_code == 200
        assert set(response.json()) == {"challenge_id", "expires_in"}
        assert response.json()["expires_in"] == 120
        assert response.headers["cache-control"] == "no-store"

    @pytest.mark.parametrize("email", ["inconnu@example.com", "client@example.com", ""])
    async def test_an_unknown_identifier_gets_the_same_response_shape(
        self, client: AsyncClient, stack: BackofficeStack, email: str
    ) -> None:
        known = await stack.identify(client)
        other = await stack.identify(client, email)

        assert other.status_code == known.status_code == 200
        assert set(other.json()) == set(known.json())
        assert len(other.json()["challenge_id"]) == len(known.json()["challenge_id"])
        assert other.headers.keys() >= {"cache-control"}
        assert other.json()["expires_in"] == known.json()["expires_in"]

    async def test_known_and_unknown_identifiers_take_a_similar_time(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        async def timed(email: str) -> float:
            started = time.perf_counter()
            await stack.identify(client, email)
            return time.perf_counter() - started

        for _ in range(3):  # echauffement
            await timed(OPERATOR_EMAIL)
        known = [await timed(OPERATOR_EMAIL) for _ in range(15)]
        unknown = [await timed("inconnu@example.com") for _ in range(15)]

        ratio = statistics.median(known) / statistics.median(unknown)
        assert 0.3 < ratio < 3.0

    async def test_the_challenge_is_stored_hashed_with_a_two_minute_life(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        digest, expires = stack.row("SELECT digest, expires_at FROM backoffice_challenges")

        assert isinstance(digest, str)
        assert digest != challenge and challenge not in digest
        assert len(digest) == 64
        assert str(expires).startswith("2026-01-01 12:02:00")

    async def test_extra_fields_are_refused(self, client: AsyncClient) -> None:
        response = await client.post(
            "/backoffice/identify", json={"email": "a@example.com", "role": "operator"}
        )

        assert response.status_code == 422


class TestThreeSteps:
    async def test_the_full_flow_gives_an_operator_token_with_amr(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = await stack.until_face_ok(client)

        response = await stack.password(client, challenge)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type", "expires_in"}
        assert "set-cookie" not in response.headers  # pas de rafraichissement
        claims = _claims(stack, body["access_token"])
        assert claims["roles"] == ["operator"]
        assert claims["amr"] == ["face", "pwd"]
        assert claims["token_use"] == "client"
        assert claims["sub"] == str(stack.operator_id)

    async def test_the_token_is_accepted_by_the_service_and_names_the_operator_role(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        token = (await stack.password(client, await stack.until_face_ok(client))).json()[
            "access_token"
        ]

        response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()["roles"] == ["operator"]

    async def test_the_classic_login_of_the_operator_never_gives_operator_nor_amr(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        login = await client.post(
            "/login", json={"email": OPERATOR_EMAIL, "password": ACCOUNT_SECRET}
        )

        claims = _claims(stack, login.json()["access_token"])

        assert claims["roles"] == []
        assert "amr" not in claims
        admin = await client.get(
            "/admin/users", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
        )
        assert admin.status_code == 403

    async def test_the_password_alone_is_refused_even_when_right(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await stack.password(client, challenge)

        assert (response.status_code, response.json()) == (401, GENERIC)

    async def test_a_refused_face_gets_the_generic_401_and_destroys_the_challenge(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        refused = await stack.face(client, challenge, OTHER_PNG)
        replay = await stack.face(client, challenge, PNG)

        assert (refused.status_code, refused.json()) == (401, GENERIC)
        assert (replay.status_code, replay.json()) == (401, GENERIC)

    async def test_a_challenge_serves_once(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = await stack.until_face_ok(client)
        assert (await stack.password(client, challenge)).status_code == 200

        replay = await stack.password(client, challenge)

        assert (replay.status_code, replay.json()) == (401, GENERIC)

    async def test_a_wrong_password_destroys_the_challenge(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = await stack.until_face_ok(client)

        wrong = await stack.password(client, challenge, WRONG)
        right = await stack.password(client, challenge)

        assert (wrong.status_code, wrong.json()) == (401, GENERIC)
        assert (right.status_code, right.json()) == (401, GENERIC)

    @pytest.mark.parametrize("token", ["inconnu", "x" * 200])
    async def test_an_unknown_challenge_is_the_generic_error(
        self, client: AsyncClient, stack: BackofficeStack, token: str
    ) -> None:
        face = await stack.face(client, token[:100])
        password = await stack.password(client, token[:100])

        assert (face.status_code, face.json()) == (401, GENERIC)
        assert (password.status_code, password.json()) == (401, GENERIC)

    async def test_an_expired_challenge_is_the_generic_error(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]
        stack.clock.current += timedelta(minutes=2, seconds=1)

        response = await stack.face(client, challenge)

        assert (response.status_code, response.json()) == (401, GENERIC)

    async def test_an_unknown_identifier_fails_at_the_face_like_a_wrong_face(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        unknown = (await stack.identify(client, "inconnu@example.com")).json()["challenge_id"]
        known = (await stack.identify(client)).json()["challenge_id"]

        a = await stack.face(client, unknown)
        b = await stack.face(client, known, OTHER_PNG)

        assert (a.status_code, a.json()) == (b.status_code, b.json()) == (401, GENERIC)

    async def test_a_customer_cannot_open_a_back_office_session(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        stack.enroll(stack.customer_id, PNG)
        challenge = (await stack.identify(client, EMAIL.replace("camille", "client"))).json()[
            "challenge_id"
        ]

        response = await stack.face(client, challenge)

        assert (response.status_code, response.json()) == (401, GENERIC)


class TestImages:
    async def test_jpeg_and_png_are_accepted(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await stack.face(client, challenge, JPEG, PNG)

        assert response.status_code == 200
        assert response.json() == {"face_ok": True}

    @pytest.mark.parametrize(
        "images",
        [[], [b64(PNG)] * 4, ["***pas-du-base64***"], [b64(b"GIF89a-pas-une-image")], [b64(b"")]],
    )
    async def test_invalid_images_are_a_422_that_never_counts(
        self, client: AsyncClient, stack: BackofficeStack, images: list[str]
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await client.post(
            "/backoffice/face", json={"challenge_id": challenge, "images": images}
        )

        assert response.status_code == 422
        assert stack.scalar("SELECT COUNT(*) FROM login_lockouts") == 0
        assert (await stack.face(client, challenge)).status_code == 200  # le defi a survecu

    async def test_an_image_over_one_megabyte_is_a_422(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]
        huge = PNG + b"\x00" * 1_048_577

        response = await stack.face(client, challenge, huge)

        assert response.status_code == 422
        assert "x" * 50 not in response.text

    async def test_the_response_never_echoes_images_or_challenge(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await stack.face(client, challenge, b"\x89PNG\r\n\x1a\n" + b"a" * 20)

        assert b64(PNG) not in response.text and challenge not in response.text

    async def test_an_invalid_template_is_a_409_and_is_logged(
        self,
        client: AsyncClient,
        stack: BackofficeStack,
        events: InMemoryBusinessEventLogger,
    ) -> None:
        stack.exec("UPDATE operator_face_templates SET template = x'00'")
        challenge = (await stack.identify(client)).json()["challenge_id"]

        response = await stack.face(client, challenge)

        assert response.status_code == 409
        assert any(e.reason == "invalid_template" for e in events.events)
        assert stack.scalar("SELECT COUNT(*) FROM login_lockouts") == 0


class TestLockouts:
    async def test_three_wrong_passwords_lock_the_password_step(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        for _ in range(3):
            await stack.password(client, await stack.until_face_ok(client), WRONG)
            stack.clock.current += timedelta(seconds=5)

        locked = await stack.password(client, await stack.until_face_ok(client))

        assert (locked.status_code, locked.json()) == (401, GENERIC)  # meme le bon mot de passe
        stack.clock.current += timedelta(minutes=5)
        ok = await stack.password(client, await stack.until_face_ok(client))
        assert ok.status_code == 200

    async def test_five_refused_faces_lock_the_face_step_but_not_the_password_counter(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        for _ in range(5):
            challenge = (await stack.identify(client)).json()["challenge_id"]
            await stack.face(client, challenge, OTHER_PNG)
            stack.clock.current += timedelta(seconds=5)

        challenge = (await stack.identify(client)).json()["challenge_id"]
        locked = await stack.face(client, challenge)

        assert (locked.status_code, locked.json()) == (401, GENERIC)
        scopes = {row[0] for row in stack.rows("SELECT scope FROM login_lockouts")}
        assert "face" in scopes and "operator_password" not in scopes

    async def test_a_complete_login_resets_the_counters(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        challenge = (await stack.identify(client)).json()["challenge_id"]
        await stack.face(client, challenge, OTHER_PNG)
        assert int(str(stack.scalar("SELECT COUNT(*) FROM login_lockouts"))) > 0

        await stack.password(client, await stack.until_face_ok(client))

        assert stack.scalar("SELECT COUNT(*) FROM login_lockouts") == 0

    async def test_a_lock_survives_in_the_database(
        self, client: AsyncClient, stack: BackofficeStack
    ) -> None:
        for _ in range(3):
            await stack.password(client, await stack.until_face_ok(client), WRONG)
            stack.clock.current += timedelta(seconds=5)

        rows = stack.rows("SELECT scope, locked_until FROM login_lockouts")

        assert any(scope == "operator_password" and until is not None for scope, until in rows)


class TestLogs:
    async def test_the_flow_logs_each_step_without_image_secret_or_challenge(
        self,
        client: AsyncClient,
        stack: BackofficeStack,
        events: InMemoryBusinessEventLogger,
    ) -> None:
        challenge = await stack.until_face_ok(client)
        await stack.password(client, challenge, WRONG)
        events_after = [e.event for e in events.events]
        text = json.dumps([repr(e) for e in events.events])

        assert "auth.backoffice_identify" in events_after
        assert "auth.backoffice_face_result" in events_after
        assert "auth.backoffice_password_result" in events_after
        for forbidden in (challenge, WRONG, ACCOUNT_SECRET, OPERATOR_EMAIL, b64(PNG), "PNG"):
            assert forbidden not in text


class TestDisabledByDefault:
    async def test_the_routes_do_not_exist_when_the_back_office_is_off(self) -> None:
        from app.core.config import Settings
        from app.main import create_app

        application = create_app(Settings(backoffice_enabled=False))

        paths = set(application.openapi()["paths"])

        assert not any(path.startswith("/backoffice") for path in paths)
