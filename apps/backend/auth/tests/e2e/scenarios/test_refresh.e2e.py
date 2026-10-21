"""Rafraichissement et deconnexion sur la pile reelle : Traefik, auth et Postgres.

Le cookie de rafraichissement est `Secure` : sur http, le client ne le renvoie pas de lui-meme,
les scenarios le passent donc a la main (l'en-tete `Cookie`), comme le ferait un navigateur en https.
"""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
CSRF = {"X-Requested-With": "basecamp-e2e"}
GENERIC_SESSION = {"detail": "Session expirée."}


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as http:
        yield http


@pytest.fixture
def session(client: httpx.Client) -> str:
    """Cookie de rafraichissement d'une connexion neuve."""
    email = f"e2e-refresh-{uuid.uuid4().hex[:10]}@example.test"
    assert (
        client.post("/api/auth/register", json={"email": email, "password": PHRASE}).status_code
        == 202
    )
    response = client.post("/api/auth/login", json={"email": email, "password": PHRASE})
    assert response.status_code == 200
    return cookie_of(response)


def cookie_of(response: httpx.Response) -> str:
    return response.headers["set-cookie"].split(";")[0].split("=", 1)[1]


def refresh(client: httpx.Client, token: str | None, headers: dict[str, str] | None = CSRF):
    cookie = {"Cookie": f"refresh_token={token}"} if token else {}
    return client.post("/api/auth/refresh", headers={**(headers or {}), **cookie})


def logout(client: httpx.Client, token: str | None, headers: dict[str, str] | None = CSRF):
    cookie = {"Cookie": f"refresh_token={token}"} if token else {}
    return client.post("/api/auth/logout", headers={**(headers or {}), **cookie})


class TestRefresh:
    def test_the_gateway_rotates_the_refresh_token(
        self, client: httpx.Client, session: str
    ) -> None:
        response = refresh(client, session)

        assert response.status_code == 200
        assert response.json()["expires_in"] == 900
        assert cookie_of(response) != session
        me = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
        )
        assert me.status_code == 200

    def test_the_csrf_header_is_mandatory(self, client: httpx.Client, session: str) -> None:
        assert refresh(client, session, headers=None).status_code == 403
        assert refresh(client, session).status_code == 200

    def test_a_replayed_token_revokes_the_whole_family(
        self, client: httpx.Client, session: str
    ) -> None:
        newest = cookie_of(refresh(client, session))

        replay = refresh(client, session)

        assert replay.status_code == 401
        assert replay.json() == GENERIC_SESSION
        assert refresh(client, newest).status_code == 401

    def test_an_unknown_or_missing_token_is_the_same_401(self, client: httpx.Client) -> None:
        for token in (None, "never-issued"):
            response = refresh(client, token)

            assert response.status_code == 401
            assert response.json() == GENERIC_SESSION
            assert "max-age=0" in response.headers["set-cookie"].lower()

    def test_of_simultaneous_refreshes_with_the_same_token_only_one_succeeds(
        self, client: httpx.Client, session: str
    ) -> None:
        contenders = 8
        start = Barrier(contenders)

        def attempt(_: int) -> int:
            with httpx.Client(base_url=BASE_URL, timeout=30.0) as http:
                start.wait()
                return refresh(http, session).status_code

        with ThreadPoolExecutor(contenders) as pool:
            statuses = list(pool.map(attempt, range(contenders)))

        assert statuses.count(200) == 1
        assert statuses.count(401) == contenders - 1


class TestLogout:
    def test_it_revokes_the_session_and_is_idempotent(
        self, client: httpx.Client, session: str
    ) -> None:
        first = logout(client, session)
        again = logout(client, session)
        anonymous = logout(client, None)

        assert (first.status_code, again.status_code, anonymous.status_code) == (204, 204, 204)
        assert "max-age=0" in first.headers["set-cookie"].lower()
        assert refresh(client, session).status_code == 401

    def test_the_csrf_header_is_mandatory(self, client: httpx.Client, session: str) -> None:
        assert logout(client, session, headers=None).status_code == 403
        assert refresh(client, session).status_code == 200
