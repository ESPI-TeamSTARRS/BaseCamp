"""Catalogue géré depuis le back-office sur la pile : routes serveur (/bff), shop, passerelle et site client.

Le navigateur n'a que son cookie de session ; le back-office relaie à `shop` avec le jeton du cookie. Le
jeton d'opérateur est signé avec la clé de développement d'`auth` (comme dans `test_catalog_admin`) : le
back-office le vérifie par le JWKS d'`auth`. La connexion en trois temps est couverte par les e2e d'`auth`.
Toutes les requêtes portent `Host: admin.localhost` ; le site client est appelé sur le domaine principal.
"""

import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
KEY_PATH = Path(
    os.environ.get(
        "E2E_AUTH_KEY", str(Path(__file__).resolve().parents[6] / ".secrets/auth/jwt-private.pem")
    )
)
ADMIN_HOST = {"Host": "admin.localhost"}
SAME_ORIGIN = {**ADMIN_HOST, "Sec-Fetch-Site": "same-origin"}
BFF = "/bff/products"
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4
CREATED: list[
    str
] = []  # produits créés ici, archivés à la fin (le catalogue d'origine reste intact)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(roles: list[str], amr: list[str]) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    pem = KEY_PATH.read_bytes()
    private = serialization.load_pem_private_key(pem, password=None)
    assert isinstance(private, Ed25519PrivateKey)
    x = _b64(private.public_key().public_bytes_raw())
    canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))
    kid = _b64(hashlib.sha256(canonical.encode()).digest())
    now = int(time.time())
    claims = {
        "iss": "basecamp-auth",
        "aud": "basecamp-client-api",
        "sub": str(uuid.uuid4()),
        "roles": roles,
        "amr": amr,
        "email_verified": True,
        "token_use": "client",
        "iat": now,
        "exp": now + 600,
        "jti": str(uuid.uuid4()),
    }
    return str(jwt.encode(claims, pem, algorithm="EdDSA", headers={"kid": kid}))


class PatientClient(httpx.Client):
    """Patiente quand la passerelle limite le débit du site client."""

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        response = super().send(request, **kwargs)
        for _ in range(8):
            if response.status_code != 429:
                break
            time.sleep(2.2)
            response = super().send(request, **kwargs)
        return response


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"bo_access={token}"}


@pytest.fixture(scope="module")
def session() -> dict[str, str]:
    return {**SAME_ORIGIN, **_cookie(_token(["operator"], ["pwd", "face"]))}


@pytest.fixture(scope="module", autouse=True)
def archive_created_products(session: dict[str, str]) -> Any:
    yield
    with PatientClient(base_url=BASE_URL, timeout=30.0, follow_redirects=False) as client:
        for product_id in CREATED:
            client.post(f"{BFF}/{product_id}/archive", headers=session)


@pytest.fixture
def client() -> Any:
    with PatientClient(base_url=BASE_URL, timeout=30.0, follow_redirects=False) as session:
        yield session


def _body(name: str | None = None) -> dict[str, Any]:
    return {
        "name": name or f"Tente BO {uuid.uuid4().hex[:10]}",
        "category": "tentes",
        "price_cents": 12900,
        "short_description": "Produit de test du back-office",
        "description": "Produit créé par le scénario e2e du back-office.",
        "specs": {"weight_grams": 1500},
        "stock": 12,
    }


def _create(
    client: httpx.Client, session: dict[str, str], name: str | None = None
) -> dict[str, Any]:
    response = client.post(BFF, json=_body(name), headers=session)
    assert response.status_code == 201, response.text
    CREATED.append(response.json()["id"])
    return dict(response.json())


class TestGuard:
    def test_the_catalog_screens_and_routes_need_a_session(self, client: httpx.Client) -> None:
        for path in ("/produits", "/produits/nouveau", "/produits/une-tente"):
            response = client.get(path, headers=ADMIN_HOST)
            assert response.status_code == 307, path
            assert response.headers["location"].endswith("/login"), path
        for method in ("GET", "POST"):
            response = client.request(method, BFF, headers=SAME_ORIGIN)
            assert (response.status_code, response.json()["detail"]) == (
                401,
                "Authentification requise.",
            )

    def test_a_token_without_the_face_factor_or_a_customer_token_opens_nothing(
        self, client: httpx.Client
    ) -> None:
        for roles, amr in ((["operator"], ["pwd"]), (["customer"], ["pwd", "face"])):
            headers = {**SAME_ORIGIN, **_cookie(_token(roles, amr))}

            assert client.get(BFF, headers=headers).status_code == 401
            assert (
                client.get(
                    "/produits", headers=ADMIN_HOST | _cookie(_token(roles, amr))
                ).status_code
                == 307
            )

    def test_a_cross_site_write_is_refused_before_reaching_shop(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        headers = {**session, "Sec-Fetch-Site": "cross-site"}

        response = client.post(BFF, json=_body(), headers=headers)

        assert response.status_code == 403 and response.json()["code"] == "cross_origin"

    def test_the_screens_are_served_with_a_session(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)

        for path, text in (
            ("/produits", "Catalogue"),
            ("/produits/nouveau", "Nouveau produit"),
            (f"/produits/{created['id']}", "Modifier le produit"),
        ):
            response = client.get(path, headers=session)
            assert response.status_code == 200 and text in response.text, path


class TestCatalogFromTheBackOffice:
    def test_price_stock_and_image_changes_are_visible_on_the_customer_site(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)
        slug = created["slug"]
        assert client.get(f"/api/shop/products/{slug}").json()["price_cents"] == 12900

        patched = client.patch(
            f"{BFF}/{created['id']}",
            json={"version": created["version"], "price_cents": 9900, "stock": 3},
            headers=session,
        )
        uploaded = client.post(
            f"{BFF}/{created['id']}/image",
            content=JPEG,
            headers={**session, "Content-Type": "image/jpeg"},
        )

        assert patched.status_code == 200 and patched.json()["version"] == created["version"] + 1
        assert uploaded.status_code == 200, uploaded.text
        (key,) = uploaded.json()["image_keys"]
        public = client.get(f"/api/shop/products/{slug}").json()
        assert public["price_cents"] == 9900
        assert public["availability"] == "low_stock"
        assert public["thumbnail_url"] == f"/media/{key}"
        media = client.get(f"/media/{key}")
        assert media.status_code == 200 and media.content == JPEG

    def test_the_list_paginates_and_searches_by_name(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        tag = uuid.uuid4().hex[:8]
        first = _create(client, session, f"Gourde Zèbre {tag} A")
        _create(client, session, f"Gourde Zèbre {tag} B")
        _create(client, session, f"Autre produit {tag}")

        found = client.get(BFF, params={"q": f"gourde zèbre {tag}", "limit": 1}, headers=session)
        second = client.get(
            BFF, params={"q": f"gourde zèbre {tag}", "limit": 1, "offset": 1}, headers=session
        )
        none = client.get(BFF, params={"q": f"introuvable-{tag}"}, headers=session)
        wildcard = client.get(BFF, params={"q": "%"}, headers=session)

        assert found.status_code == 200 and found.json()["total"] == 2
        assert [i["id"] for i in found.json()["items"]] != [i["id"] for i in second.json()["items"]]
        assert none.json()["total"] == 0
        assert first["id"] in {i["id"] for i in found.json()["items"] + second.json()["items"]}
        assert wildcard.json()["total"] == 0  # « % » est cherché tel quel, jamais comme un joker

    def test_a_stale_version_is_a_409_with_a_clear_message_and_the_reload_gives_the_new_one(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)
        client.patch(
            f"{BFF}/{created['id']}",
            json={"version": created["version"], "stock": 5},
            headers=session,
        )

        stale = client.patch(
            f"{BFF}/{created['id']}",
            json={"version": created["version"], "stock": 1},
            headers=session,
        )
        latest = client.get(f"{BFF}/{created['id']}", headers=session).json()

        assert stale.status_code == 409 and stale.json()["code"] == "stale_version"
        assert "modifié ailleurs" in stale.json()["detail"]
        assert latest["stock"] == 5 and latest["version"] == created["version"] + 1

    def test_archiving_removes_the_product_from_the_site_and_the_filter_shows_it(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)

        archived = client.post(f"{BFF}/{created['id']}/archive", headers=session)
        again = client.patch(
            f"{BFF}/{created['id']}",
            json={"version": archived.json()["version"], "stock": 1},
            headers=session,
        )
        default = client.get(BFF, params={"limit": 100}, headers=session).json()
        with_archived = client.get(
            BFF, params={"limit": 100, "include_archived": "true"}, headers=session
        ).json()

        assert archived.status_code == 200 and archived.json()["archived_at"] is not None
        assert client.get(f"/api/shop/products/{created['slug']}").status_code == 404
        assert again.status_code == 409 and again.json()["code"] == "archived"
        assert created["id"] not in {i["id"] for i in default["items"]}
        assert created["id"] in {i["id"] for i in with_archived["items"]}

    def test_a_duplicate_a_missing_product_and_invalid_input_have_fixed_messages(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)

        duplicate = client.post(BFF, json={**_body(), "slug": created["slug"]}, headers=session)
        missing = client.get(f"{BFF}/n-existe-pas", headers=session)
        invalid = client.post(BFF, json={**_body(), "price_cents": -1}, headers=session)
        extra = client.post(BFF, json={**_body(), "rating_value": 5}, headers=session)
        bad_json = client.post(BFF, content=b"{pas du json", headers=session)

        assert (duplicate.status_code, duplicate.json()["code"]) == (409, "duplicate")
        assert (missing.status_code, missing.json()["detail"]) == (404, "Produit introuvable.")
        assert (invalid.status_code, extra.status_code, bad_json.status_code) == (422, 422, 400)
        assert "rating_value" not in extra.text and "price_cents" not in invalid.text

    def test_a_refused_image_says_why_and_changes_nothing(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        created = _create(client, session)
        path = f"{BFF}/{created['id']}/image"
        headers = {**session, "Content-Type": "image/jpeg"}

        disguised = client.post(path, content=b"<?php echo 1; ?>", headers=headers)
        big = client.post(path, content=JPEG + bytes(2 * 1024 * 1024), headers=headers)

        for refused in (disguised, big):
            assert refused.status_code in (413, 422)
            assert refused.json()["detail"] == "Image refusée : JPEG, PNG ou WebP, 2 Mo au plus."
        assert client.get(f"{BFF}/{created['id']}", headers=session).json()["image_keys"] == []
