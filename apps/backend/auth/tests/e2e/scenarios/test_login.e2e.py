"""Connexion sur la pile reelle : Traefik, auth et Postgres (aucun jeton ni mot de passe journalise).

Chaque scenario cree son compte par l'API publique (`/register`) : un compte non verifie peut se
connecter, donc la boite mail n'est pas necessaire. Le scenario « compte desactive » et le
controle des journaux passent par `docker compose` (E2E_CHECK_LOGS=1).
"""

import base64
import json
import os
import shutil
import statistics
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]  # docker compose se lance depuis la racine
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
ISSUER = "basecamp-auth"
AUDIENCE = "basecamp-client-api"
GENERIC_LOGIN = {"detail": "Identifiants invalides."}
GENERIC_TOKEN = {"detail": "Authentification requise."}
needs_docker = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as http:
        yield http


@pytest.fixture
def address(client: httpx.Client) -> str:
    email = f"e2e-login-{uuid.uuid4().hex[:10]}@example.test"
    assert (
        client.post("/api/auth/register", json={"email": email, "password": PHRASE}).status_code
        == 202
    )
    return email


def login(client: httpx.Client, email: str, password: str = PHRASE) -> httpx.Response:
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def published_key(client: httpx.Client, kid: str) -> Any:
    keys = client.get("/.well-known/jwks.json").json()["keys"]
    return jwt.PyJWK(next(key for key in keys if key["kid"] == kid)).key


class TestLogin:
    def test_login_returns_a_token_verifiable_with_the_published_key(
        self, client: httpx.Client, address: str
    ) -> None:
        response = login(client, address)

        assert response.status_code == 200
        body = response.json()
        assert (body["token_type"], body["expires_in"]) == ("Bearer", 900)
        kid = jwt.get_unverified_header(body["access_token"])["kid"]
        claims = jwt.decode(
            body["access_token"],
            published_key(client, kid),
            algorithms=["EdDSA"],
            audience=AUDIENCE,
            issuer=ISSUER,
        )
        assert set(claims) == {
            "iss", "aud", "sub", "roles", "email_verified", "token_use", "iat", "exp", "jti",
        }  # fmt: skip
        assert claims["roles"] == ["customer"]
        assert claims["email_verified"] is False
        assert claims["token_use"] == "client"
        assert claims["exp"] - claims["iat"] == 900

    def test_the_refresh_token_is_a_strict_httponly_secure_cookie_scoped_to_auth(
        self, client: httpx.Client, address: str
    ) -> None:
        response = login(client, address)

        cookie = response.headers["set-cookie"]
        attributes = {part.strip().lower() for part in cookie.split(";")}
        assert {"httponly", "secure", "samesite=strict", "path=/api/auth"} <= attributes
        assert response.json()["access_token"] not in cookie
        assert response.headers["cache-control"] == "no-store"

    def test_me_returns_the_profile_for_a_valid_token(
        self, client: httpx.Client, address: str
    ) -> None:
        token = login(client, address).json()["access_token"]

        response = client.get("/api/auth/me", headers=bearer(token))

        assert response.status_code == 200
        profile = response.json()
        assert (profile["email"], profile["roles"], profile["email_verified"]) == (
            address,
            ["customer"],
            False,
        )
        assert "password" not in response.text

    def test_me_refuses_forged_unsigned_and_missing_tokens_with_the_same_401(
        self, client: httpx.Client, address: str
    ) -> None:
        token = login(client, address).json()["access_token"]
        header, payload, signature = token.split(".")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
        forged = f"{header}.{b64({**claims, 'roles': ['operator']})}.{signature}"
        unsigned = f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': 'x'})}.{b64(claims)}."

        responses = [
            client.get("/api/auth/me", headers=bearer(forged)),
            client.get("/api/auth/me", headers=bearer(unsigned)),
            client.get("/api/auth/me", headers=bearer("pas.un.jeton")),
            client.get("/api/auth/me"),
        ]

        for response in responses:
            assert response.status_code == 401
            assert response.json() == GENERIC_TOKEN

    def test_jwks_is_published_by_the_gateway_without_any_private_parameter(
        self, client: httpx.Client
    ) -> None:
        direct = client.get("/.well-known/jwks.json")
        prefixed = client.get("/api/auth/.well-known/jwks.json")

        assert direct.status_code == prefixed.status_code == 200
        assert direct.json() == prefixed.json()
        for key in direct.json()["keys"]:
            assert {"kty", "crv", "kid", "x"} <= set(key)
            assert "d" not in key
            assert key["alg"] == "EdDSA"

    def test_internal_routes_stay_unreachable(self, client: httpx.Client) -> None:
        assert client.get("/api/auth/internal/jwks").status_code == 404


class TestGenericRefusal:
    def test_wrong_password_unknown_email_and_bad_input_do_not_reveal_the_account(
        self, client: httpx.Client, address: str
    ) -> None:
        wrong = login(client, address, "mauvais-mot-de-passe-42")
        unknown = login(client, f"inconnu-{uuid.uuid4().hex[:8]}@example.test")

        for response in (wrong, unknown):
            assert response.status_code == 401
            assert response.json() == GENERIC_LOGIN
            assert "set-cookie" not in response.headers
        assert wrong.content == unknown.content

    def test_response_time_does_not_reveal_whether_the_email_exists(
        self, client: httpx.Client, address: str
    ) -> None:
        unknown = f"inconnu-{uuid.uuid4().hex[:8]}@example.test"
        login(client, address, "echauffement-42")

        known_times = [self._timed(client, address) for _ in range(5)]
        unknown_times = [self._timed(client, unknown) for _ in range(5)]

        assert abs(statistics.median(known_times) - statistics.median(unknown_times)) < 0.5

    @staticmethod
    def _timed(client: httpx.Client, email: str) -> float:
        start = time.perf_counter()
        assert login(client, email, "mauvais-mot-de-passe-42").status_code == 401
        return time.perf_counter() - start

    def test_unknown_field_is_refused_without_being_reflected(
        self, client: httpx.Client, address: str
    ) -> None:
        response = client.post(
            "/api/auth/login", json={"email": address, "password": PHRASE, "role": "operator"}
        )

        assert response.status_code == 422
        assert "operator" not in response.text
        assert PHRASE not in response.text


@needs_docker
class TestDisabledAccountAndLogs:
    def test_a_disabled_account_gets_the_same_401_and_loses_its_token(
        self, client: httpx.Client, address: str
    ) -> None:
        token = login(client, address).json()["access_token"]

        self._sql(f"UPDATE users SET disabled_at = now() WHERE email = '{address}'")  # noqa: S608
        refused = login(client, address)
        me = client.get("/api/auth/me", headers=bearer(token))

        assert (refused.status_code, refused.json()) == (401, GENERIC_LOGIN)
        assert (me.status_code, me.json()) == (401, GENERIC_TOKEN)

    def test_container_logs_hold_no_password_token_cookie_key_or_address(
        self, client: httpx.Client
    ) -> None:
        address = f"e2e-logs-{uuid.uuid4().hex[:10]}@example.test"
        phrase = "journal-" + uuid.uuid4().hex
        assert (
            client.post(
                "/api/auth/register", json={"email": address, "password": phrase}
            ).status_code
            == 202
        )
        ok = login(client, address, phrase)
        login(client, address, "mauvais-" + uuid.uuid4().hex)
        refresh = ok.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        token = ok.json()["access_token"]
        client.get("/api/auth/me", headers=bearer(token + "x"))

        logs = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "auth", "traefik"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
            cwd=REPO_ROOT,
        ).stdout

        assert "auth.login_succeeded" in logs
        assert "auth.login_failed" in logs
        for secret in (phrase, token, token.split(".")[1], refresh, address, "BEGIN PRIVATE KEY"):
            assert secret not in logs

    @staticmethod
    def _sql(statement: str) -> None:
        command = ["docker", "compose", "exec", "-T", "postgres-auth"]
        command += ["psql", "-U", "auth", "-d", "auth", "-c", statement]
        subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, timeout=180, check=True, cwd=REPO_ROOT
        )
