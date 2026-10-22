"""Session du back-office sur la pile : connexion en trois temps par les routes serveur, garde, déconnexion.

Tout passe par la passerelle sur l'hôte du back-office (`Host: mercure.localhost`). Le navigateur appelle les routes
serveur du back-office (`/session/identify`, `/face`, `/password`) ; la dernière pose un cookie `HttpOnly`
et ne renvoie jamais le jeton. Les cookies sont gérés à la main (le jar d'httpx lie les cookies au nom
d'hôte de l'URL, ici une adresse IP). Opérateur créé et visage enrôlé comme dans les e2e de WORK-59.
"""

import base64
import json
import os
import shutil
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.backoffice.__tests__.real_stack import (
    ADMIN_HOST,
    BASE_URL,
    FACE,
    OTHER_FACE,
    PHRASE,
    b64,
    compose,
    new_operator,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
ADMIN = {"Host": ADMIN_HOST}
SAME_ORIGIN = {**ADMIN, "Sec-Fetch-Site": "same-origin"}
GENERIC = {"detail": "Identifiants invalides."}


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30.0, follow_redirects=False) as session:
        yield session


def _step(client: httpx.Client, step: str, body: dict[str, Any], **headers: str) -> httpx.Response:
    return client.post(f"/session/{step}", json=body, headers={**SAME_ORIGIN, **headers})


def _login(
    client: httpx.Client, email: str, face: bytes = FACE, password: str = PHRASE
) -> httpx.Response:
    """Les trois temps par le back-office ; rend la réponse de la dernière étape atteinte."""
    identified = _step(client, "identify", {"email": email})
    assert identified.status_code == 200, identified.text
    challenge = identified.json()["challenge_id"]
    shown = _step(client, "face", {"challenge_id": challenge, "images": [b64(face)]})
    if shown.status_code != 200:
        return shown
    return _step(client, "password", {"challenge_id": challenge, "password": password})


def _cookie(response: httpx.Response) -> str:
    for line in response.headers.get_list("set-cookie"):
        name, _, rest = line.partition("=")
        if name.strip() == "bo_access":
            return rest.split(";", 1)[0]
    raise AssertionError("pas de cookie de session")


def _get(client: httpx.Client, path: str, cookie: str | None = None) -> httpx.Response:
    headers = dict(ADMIN)
    if cookie is not None:
        headers["Cookie"] = f"bo_access={cookie}"
    return client.get(path, headers=headers)


def _claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    return dict(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))))


class TestRouteGuard:
    def test_every_page_without_a_session_redirects_to_the_login(
        self, client: httpx.Client
    ) -> None:
        for path in ("/", "/produits", "/n-importe-quoi"):
            response = _get(client, path)

            assert response.status_code == 307, path
            assert response.headers["location"].endswith("/login"), path

    def test_the_login_page_is_public_and_the_main_domain_never_serves_it(
        self, client: httpx.Client
    ) -> None:
        assert _get(client, "/login").status_code == 200
        assert client.get("/login").status_code == 404  # domaine principal : le front répond
        assert client.post("/session/password", json={}).status_code in (404, 405)

    def test_the_bff_answers_401_json_without_a_session(self, client: httpx.Client) -> None:
        response = _get(client, "/bff/produits")

        assert (response.status_code, response.json()) == (
            401,
            {"detail": "Authentification requise."},
        )

    def test_a_forged_or_customer_token_never_opens_the_back_office(
        self, client: httpx.Client
    ) -> None:
        def part(value: dict[str, Any]) -> str:
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

        forged = f"{part({'alg': 'EdDSA', 'kid': 'x'})}.{part({'exp': 4102444800, 'roles': ['operator'], 'amr': ['face']})}.AAAA"
        operator = new_operator()
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
            classic = site.post("/api/auth/login", json={"email": operator, "password": PHRASE})
        classic_token = classic.json()["access_token"]  # connexion classique : ni operator ni amr

        assert _get(client, "/", forged).status_code == 307
        assert _get(client, "/", classic_token).status_code == 307
        assert _get(client, "/", "n-importe-quoi").status_code == 307


class TestLoginInThreeSteps:
    def test_the_operator_gets_an_http_only_cookie_and_never_sees_the_token(
        self, client: httpx.Client
    ) -> None:
        email = new_operator()

        response = _login(client, email)

        assert response.status_code == 200 and response.json() == {"ok": True}
        raw = response.headers.get_list("set-cookie")
        assert len(raw) == 1 and "HttpOnly" in raw[0] and "SameSite=strict" in raw[0]
        token = _cookie(response)
        assert token not in response.text
        claims = _claims(token)
        assert claims["roles"] == ["operator"] and claims["amr"] == ["face", "pwd"]
        home = _get(client, "/", token)
        assert home.status_code == 200 and "Se déconnecter" in home.text and token not in home.text

    def test_wrong_face_wrong_password_and_unknown_account_all_get_the_same_generic_401(
        self, client: httpx.Client
    ) -> None:
        email = new_operator()

        wrong_face = _login(client, email, face=OTHER_FACE)
        wrong_password = _login(client, email, password="pas-le-bon-mot-de-passe-1")
        unknown = _login(client, "inconnu.e2e@example.test")

        for response in (wrong_face, wrong_password, unknown):
            assert (response.status_code, response.json()) == (401, GENERIC)
            assert response.headers.get_list("set-cookie") == []

    def test_the_session_token_is_accepted_by_the_shop_admin_api_through_the_gateway(
        self, client: httpx.Client
    ) -> None:
        token = _cookie(_login(client, new_operator()))

        with httpx.Client(base_url=BASE_URL, timeout=30.0) as site:
            admin = site.get(
                "/api/shop/admin/products?limit=1",
                headers={**ADMIN, "Authorization": f"Bearer {token}"},
            )

        assert admin.status_code == 200 and "items" in admin.json()

    def test_a_post_that_does_not_come_from_the_back_office_is_refused(
        self, client: httpx.Client
    ) -> None:
        for step in ("identify", "face", "password"):
            response = client.post(
                f"/session/{step}", json={}, headers={**ADMIN, "Sec-Fetch-Site": "cross-site"}
            )

            assert response.status_code == 403, step

    def test_invalid_bodies_are_422_without_reaching_auth(self, client: httpx.Client) -> None:
        assert _step(client, "identify", {"email": "pas-une-adresse"}).status_code == 422
        assert _step(client, "face", {"challenge_id": "court", "images": []}).status_code == 422
        assert _step(client, "password", {"challenge_id": "x"}).status_code == 422


class TestLogout:
    def test_the_logout_clears_the_cookie_and_the_pages_close_again(
        self, client: httpx.Client
    ) -> None:
        token = _cookie(_login(client, new_operator()))
        assert _get(client, "/", token).status_code == 200

        out = client.post(
            "/session/logout", headers={**SAME_ORIGIN, "Cookie": f"bo_access={token}"}
        )

        assert out.status_code == 303 and out.headers["location"].endswith("/login")
        assert any("Max-Age=0" in line for line in out.headers.get_list("set-cookie"))
        assert _get(client, "/", None).status_code == 307

    def test_a_cross_site_logout_is_refused(self, client: httpx.Client) -> None:
        response = client.post("/session/logout", headers={**ADMIN, "Sec-Fetch-Site": "cross-site"})

        assert response.status_code == 403


class TestLogs:
    def test_the_login_is_logged_with_a_hash_and_never_a_secret(self, client: httpx.Client) -> None:
        email = new_operator()
        response = _login(client, email)
        token = _cookie(response)
        identified = _step(client, "identify", {"email": email})
        challenge = identified.json()["challenge_id"]
        _step(
            client, "password", {"challenge_id": challenge, "password": "pas-le-bon-mot-de-passe-2"}
        )

        logs = compose("logs", "backoffice", "--no-color", "--tail", "300").stdout
        events = [
            json.loads(line[line.index("{") :])
            for line in logs.splitlines()
            if "backoffice.login_" in line
        ]

        names = {event["event"] for event in events}
        assert {
            "backoffice.login_identify",
            "backoffice.login_face",
            "backoffice.login_password",
        } <= names
        hashed = [event for event in events if "attributes" in event]
        assert hashed and all(len(event["attributes"]["email_hash"]) == 16 for event in hashed)
        for secret in (email, PHRASE, "pas-le-bon-mot-de-passe-2", token, challenge):
            assert secret not in logs
