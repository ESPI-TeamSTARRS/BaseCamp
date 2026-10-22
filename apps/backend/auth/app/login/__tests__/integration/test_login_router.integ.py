import base64
import json
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL, ISSUER, LoginStack
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner

GENERIC_LOGIN_BODY = {"detail": "Identifiants invalides."}
GENERIC_TOKEN_BODY = {"detail": "Authentification requise."}


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[LoginStack]:
    stack = LoginStack(events)
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


def shared_headers(response: Response) -> list[tuple[str, str]]:
    return [(k, v) for k, v in response.headers.items() if k != "x-correlation-id"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class TestLogin:
    async def test_returns_the_access_token_in_the_body_and_the_refresh_token_in_a_cookie(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        user_id = stack.add_account()

        response = await login(client)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"access_token", "token_type", "expires_in"}
        assert (body["token_type"], body["expires_in"]) == ("Bearer", 900)
        claims = jwt.decode(body["access_token"], options={"verify_signature": False})
        assert claims["sub"] == str(user_id)
        assert claims["exp"] - claims["iat"] == 900
        assert response.headers["cache-control"] == "no-store"

    async def test_the_refresh_cookie_is_httponly_secure_strict_and_scoped_to_the_auth_path(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()

        response = await login(client)

        cookie = response.headers["set-cookie"]
        attributes = {part.strip().lower() for part in cookie.split(";")}
        assert {"httponly", "secure", "samesite=strict", "path=/api/auth"} <= attributes
        assert "max-age=604800" in attributes
        assert cookie.startswith("refresh_token=")
        assert response.json()["access_token"] not in cookie

    async def test_only_the_hash_of_the_refresh_token_is_stored(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()

        response = await login(client)

        raw = response.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        stored = stack.scalar("SELECT token_hash FROM refresh_tokens")
        assert stored != raw
        assert len(str(stored)) == 64
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 1

    async def test_an_unverified_account_can_log_in_with_email_verified_false(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account(verified=False)

        body = (await login(client)).json()

        claims = jwt.decode(body["access_token"], options={"verify_signature": False})
        assert claims["email_verified"] is False

    async def test_every_failure_is_the_same_generic_401_without_cookie(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account(email="actif@example.com")
        stack.add_account(email="ferme@example.com", disabled=True)

        responses = [
            await login(client, "actif@example.com", "mauvais-mot-de-passe"),
            await login(client, "inconnu@example.com", ACCOUNT_SECRET),
            await login(client, "ferme@example.com", ACCOUNT_SECRET),
        ]

        for response in responses:
            assert response.status_code == 401
            assert response.json() == GENERIC_LOGIN_BODY
            assert "set-cookie" not in response.headers
        assert len({r.content for r in responses}) == 1
        assert len({tuple(sorted(shared_headers(r))) for r in responses}) == 1
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 0

    @pytest.mark.parametrize(
        "body",
        [
            {"email": EMAIL},
            {"password": ACCOUNT_SECRET},
            {"email": EMAIL, "password": ACCOUNT_SECRET, "role": "operator"},
            {"email": 12, "password": ACCOUNT_SECRET},
            {"email": EMAIL, "password": "x" * 300},
            {},
        ],
    )
    async def test_invalid_input_is_a_sanitized_422_that_never_echoes_the_password(
        self, client: AsyncClient, body: dict[str, Any]
    ) -> None:
        response = await client.post("/login", json=body)

        assert response.status_code == 422
        assert response.json()["detail"] == "Requete invalide."
        assert "x" * 300 not in response.text
        assert "operator" not in response.text
        assert ACCOUNT_SECRET not in response.text

    async def test_a_known_account_login_is_logged_with_the_forwarded_client_ip(
        self, client: AsyncClient, stack: LoginStack, events: InMemoryBusinessEventLogger
    ) -> None:
        stack.add_account()

        await client.post(
            "/login",
            json={"email": EMAIL, "password": "mauvais-mot-de-passe"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )

        assert events.events[0].client_ip == "203.0.113.9"
        assert events.events[0].event == "auth.login_failed"

    async def test_a_forwarded_address_is_ignored_when_the_peer_is_not_a_trusted_proxy(
        self, client: AsyncClient, stack: LoginStack, events: InMemoryBusinessEventLogger
    ) -> None:
        from app.core.client_address_resolver import ClientAddressResolver

        stack.application.state.client_address_resolver = ClientAddressResolver.from_text("")

        await client.post(
            "/login",
            json={"email": EMAIL, "password": "mauvais-mot-de-passe"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        )

        assert events.events[0].client_ip == "127.0.0.1"

    @pytest.mark.parametrize("forwarded", ["pas-une-ip\nforge", "", "999.1.1.1"])
    async def test_an_invalid_forwarded_address_is_never_logged(
        self,
        client: AsyncClient,
        events: InMemoryBusinessEventLogger,
        forwarded: str,
    ) -> None:
        await client.post(
            "/login",
            json={"email": EMAIL, "password": ACCOUNT_SECRET},
            headers={"X-Forwarded-For": forwarded},
        )

        assert events.events[0].client_ip == "127.0.0.1"


class TestMe:
    async def test_a_valid_token_returns_the_profile(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        user_id = stack.add_account(role="operator", verified=False)
        token = (await login(client)).json()["access_token"]

        response = await client.get("/me", headers=bearer(token))

        assert response.status_code == 200
        assert response.json() == {
            "id": str(user_id),
            "email": EMAIL,
            "roles": ["operator"],
            "email_verified": False,
        }
        assert response.headers["cache-control"] == "no-store"
        assert "password" not in response.text

    async def test_the_scheme_is_case_insensitive(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()
        token = (await login(client)).json()["access_token"]

        response = await client.get("/me", headers={"Authorization": f"bearer {token}"})

        assert response.status_code == 200

    async def test_an_expired_token_is_a_generic_401(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()
        token = (await login(client)).json()["access_token"]
        stack.clock.current += timedelta(minutes=15)

        response = await client.get("/me", headers=bearer(token))

        assert response.status_code == 401
        assert response.json() == GENERIC_TOKEN_BODY
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_a_forged_token_is_the_same_generic_401(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()
        header, payload, signature = (await login(client)).json()["access_token"].split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        forged = f"{header}.{b64({**claims, 'roles': ['operator']})}.{signature}"

        response = await client.get("/me", headers=bearer(forged))

        assert (response.status_code, response.json()) == (401, GENERIC_TOKEN_BODY)

    async def test_a_token_without_signature_alg_none_is_the_same_generic_401(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        user_id = stack.add_account()
        token = (await login(client)).json()["access_token"]
        claims = jwt.decode(token, options={"verify_signature": False})
        claims["sub"] = str(user_id)
        unsigned = (
            f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': stack.keys.signing_kid})}.{b64(claims)}."
        )

        response = await client.get("/me", headers=bearer(unsigned))

        assert (response.status_code, response.json()) == (401, GENERIC_TOKEN_BODY)

    async def test_a_token_for_another_audience_is_the_same_generic_401(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        user_id = stack.add_account()
        claims = AccessTokenClaims(
            user_id,
            ("customer",),
            True,
            stack.clock.current,
            stack.clock.current + timedelta(hours=1),
            "jti",
        )
        other = JwtAccessTokenSigner(stack.keys, ISSUER, "payment-service").sign(claims)

        response = await client.get("/me", headers=bearer(other))

        assert (response.status_code, response.json()) == (401, GENERIC_TOKEN_BODY)

    @pytest.mark.parametrize(
        "headers",
        [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}, {"Authorization": ""}],
    )
    async def test_a_missing_or_malformed_header_is_the_same_generic_401(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.get("/me", headers=headers)

        assert (response.status_code, response.json()) == (401, GENERIC_TOKEN_BODY)
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_a_disabled_account_loses_access_immediately(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()
        token = (await login(client)).json()["access_token"]
        with stack.engine.begin() as connection:
            connection.exec_driver_sql("UPDATE users SET disabled_at = '2026-01-01 12:00:00'")

        response = await client.get("/me", headers=bearer(token))

        assert (response.status_code, response.json()) == (401, GENERIC_TOKEN_BODY)


class TestJwks:
    async def test_publishes_the_public_key_with_its_kid_and_never_the_private_one(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        response = await client.get("/.well-known/jwks.json")

        assert response.status_code == 200
        (key,) = response.json()["keys"]
        assert key == {
            "kty": "OKP",
            "crv": "Ed25519",
            "use": "sig",
            "alg": "EdDSA",
            "kid": stack.keys.signing_kid,
            "x": stack.keys.public_keys()[0].x,
        }
        assert "d" not in key
        assert "public" in response.headers["cache-control"]

    async def test_the_kid_of_a_token_is_published(
        self, client: AsyncClient, stack: LoginStack
    ) -> None:
        stack.add_account()
        token = (await login(client)).json()["access_token"]

        published = {k["kid"] for k in (await client.get("/.well-known/jwks.json")).json()["keys"]}

        assert jwt.get_unverified_header(token)["kid"] in published


class TestRotationOverHttp:
    async def test_tokens_of_the_previous_key_still_work_and_both_keys_are_published(
        self, events: InMemoryBusinessEventLogger
    ) -> None:
        old_stack = LoginStack(events)
        user_id = old_stack.add_account()
        async with AsyncClient(
            transport=ASGITransport(app=old_stack.application), base_url="http://test"
        ) as old_client:
            old_token = (await login(old_client)).json()["access_token"]
        rotated = Ed25519KeyRing(
            Ed25519KeyRing.generate().signing_key, [old_stack.keys.signing_public_key]
        )
        new_stack = LoginStack(events, keys=rotated)
        new_stack.add_account(user_id=user_id)

        async with AsyncClient(
            transport=ASGITransport(app=new_stack.application), base_url="http://test"
        ) as client:
            me = await client.get("/me", headers=bearer(old_token))
            keys = (await client.get("/.well-known/jwks.json")).json()["keys"]
            new_token = (await login(client)).json()["access_token"]

        assert me.status_code == 200
        assert [k["kid"] for k in keys] == [rotated.signing_kid, old_stack.keys.signing_kid]
        assert jwt.get_unverified_header(new_token)["kid"] == rotated.signing_kid
        old_stack.engine.dispose()
        new_stack.engine.dispose()
