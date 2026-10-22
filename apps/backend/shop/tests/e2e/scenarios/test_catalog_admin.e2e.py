"""Administration du catalogue sur la pile : origine admin, garde par JWKS, image dans le bucket, archivage.

Le jeton d'opérateur est signé avec la clé de développement d'`auth` (`.secrets/auth/jwt-private.pem`,
générée par `scripts/init-auth-keys.sh`, jamais versionnée) : `shop` le vérifie par le JWKS publié par
`auth`, exactement comme un vrai jeton. Les requêtes d'administration portent `Host: admin.localhost`
(la passerelle ne route `/api/shop/admin` que sur une origine `admin.*`).
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
ADMIN = "/api/shop/admin/products"
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4
RATE_LIMIT_PAUSE_SECONDS = 6.5
RATE_LIMIT_ATTEMPTS = 8


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(roles: list[str], amr: list[str]) -> str:
    """Jeton au format d'`auth`, signé par sa clé de développement (kid = empreinte RFC 7638)."""
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


@pytest.fixture(scope="module")
def operator() -> dict[str, str]:
    return {**ADMIN_HOST, "Authorization": f"Bearer {_token(['operator'], ['pwd', 'face'])}"}


class PatientClient(httpx.Client):
    """Client qui patiente quand la passerelle limite le débit (un jeton revient toutes les 2 s)."""

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        response = super().send(request, **kwargs)
        for _ in range(RATE_LIMIT_ATTEMPTS):
            if response.status_code != 429:
                break
            time.sleep(2.2)
            response = super().send(request, **kwargs)
        return response


@pytest.fixture(scope="module", autouse=True)
def archive_created_products(operator: dict[str, str]) -> Any:
    """Les autres scénarios attendent le catalogue d'origine : tout produit créé ici est archivé."""
    yield
    with PatientClient(base_url=BASE_URL, timeout=20.0) as client:
        for product_id in CREATED:
            client.post(f"{ADMIN}/{product_id}/archive", headers=operator)


@pytest.fixture
def client() -> httpx.Client:
    return PatientClient(base_url=BASE_URL, timeout=20.0)


def _new_body() -> dict[str, Any]:
    name = f"Tente E2E {uuid.uuid4().hex[:10]}"
    return {
        "name": name,
        "category": "tentes",
        "price_cents": 12900,
        "short_description": "Produit de test e2e",
        "description": "Produit créé par le scénario e2e d'administration.",
        "specs": {"weight_grams": 1500},
        "stock": 12,
    }


CREATED: list[
    str
] = []  # produits créés par les scénarios, archivés à la fin (le catalogue reste à 15)


def _create(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(ADMIN, json=_new_body(), headers=headers)
    assert response.status_code == 201, response.text
    CREATED.append(response.json()["id"])
    return dict(response.json())


def _order(client: httpx.Client, product_id: str) -> dict[str, Any]:
    body = {
        "email": f"e2e.admin.{uuid.uuid4().hex[:8]}@example.org",
        "shippingAddress": {
            "fullName": "Client E2E",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": product_id, "quantity": 1}],
    }
    for _ in range(RATE_LIMIT_ATTEMPTS):
        response = client.post(
            "/api/shop/orders", json=body, headers={"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"}
        )
        if response.status_code != 429:
            break
        time.sleep(RATE_LIMIT_PAUSE_SECONDS)
    assert response.status_code == 201, response.text
    return {**response.json(), "email": body["email"]}


class TestOriginAndGuard:
    def test_the_admin_api_answers_only_on_the_admin_origin(
        self, client: httpx.Client, operator: dict[str, str]
    ) -> None:
        on_admin = client.get(ADMIN, headers=operator)
        on_main = client.get(ADMIN, headers={"Authorization": operator["Authorization"]})
        on_main_post = client.post(
            ADMIN, json=_new_body(), headers={"Authorization": operator["Authorization"]}
        )

        assert on_admin.status_code == 200
        assert on_main.status_code == 404 and on_main_post.status_code in (404, 405)
        assert "application/json" not in on_main.headers.get(
            "content-type", ""
        )  # page 404 du front, pas shop

    def test_without_a_token_401_with_a_customer_or_without_face_403(
        self, client: httpx.Client
    ) -> None:
        customer = {
            **ADMIN_HOST,
            "Authorization": f"Bearer {_token(['customer'], ['pwd', 'face'])}",
        }
        no_face = {**ADMIN_HOST, "Authorization": f"Bearer {_token(['operator'], ['pwd'])}"}

        assert client.get(ADMIN, headers=ADMIN_HOST).status_code == 401
        assert (
            client.get(ADMIN, headers={**ADMIN_HOST, "Authorization": "Bearer x.y.z"}).status_code
            == 401
        )
        assert client.get(ADMIN, headers=customer).status_code == 403
        assert client.post(ADMIN, json=_new_body(), headers=customer).status_code == 403
        assert client.get(ADMIN, headers=no_face).status_code == 403


class TestCatalogAdministration:
    def test_create_edit_with_concurrency_and_archive_keep_past_orders_readable(
        self, client: httpx.Client, operator: dict[str, str]
    ) -> None:
        created = _create(client, operator)
        slug, product_id = created["slug"], created["id"]
        assert client.get(f"/api/shop/products/{slug}").status_code == 200

        order = _order(client, product_id)
        # Une commande retire du stock : la version change, une édition lue avant est périmée.
        current = client.get(f"{ADMIN}/{product_id}", headers=operator).json()
        assert current["version"] > created["version"] and current["stock"] == created["stock"] - 1
        patched = client.patch(
            f"{ADMIN}/{product_id}",
            json={"version": current["version"], "price_cents": 9900},
            headers=operator,
        )
        stale = client.patch(
            f"{ADMIN}/{product_id}",
            json={"version": created["version"], "stock": 1},
            headers=operator,
        )
        archived = client.post(f"{ADMIN}/{product_id}/archive", headers=operator)

        assert patched.status_code == 200 and patched.json()["price_cents"] == 9900
        assert stale.status_code == 409
        assert archived.status_code == 200 and archived.json()["archived_at"] is not None
        assert client.get(f"/api/shop/products/{slug}").status_code == 404
        listed = client.get(f"{ADMIN}?include_archived=true&limit=100", headers=operator).json()
        assert product_id in {item["id"] for item in listed["items"]}
        lookup = client.post(
            "/api/shop/orders/lookup",
            json={"orderNumber": order["number"], "email": order["email"]},
        )
        assert lookup.status_code == 200 and lookup.json()["number"] == order["number"]
        assert lookup.json()["lines"][0]["name"] == created["name"]

    def test_invalid_input_is_a_sanitized_422_and_extra_fields_are_refused(
        self, client: httpx.Client, operator: dict[str, str]
    ) -> None:
        for patch in ({"price_cents": -1}, {"stock": 1.5}, {"rating_value": 5}, {"name": ""}):
            response = client.post(ADMIN, json={**_new_body(), **patch}, headers=operator)

            assert response.status_code == 422, patch
            assert "rating_value" not in response.text


class TestImages:
    def test_an_uploaded_image_is_served_by_media_from_the_bucket(
        self, client: httpx.Client, operator: dict[str, str]
    ) -> None:
        created = _create(client, operator)

        uploaded = client.post(
            f"{ADMIN}/{created['id']}/image",
            content=JPEG,
            headers={**operator, "Content-Type": "image/jpeg"},
        )

        assert uploaded.status_code == 200, uploaded.text
        (key,) = uploaded.json()["image_keys"]
        assert key.endswith(".jpg") and len(key) == 36
        media = client.get(f"/media/{key}")
        assert media.status_code == 200 and media.content == JPEG
        public = client.get(f"/api/shop/products/{created['slug']}").json()
        assert public["thumbnail_url"] == f"/media/{key}"

    def test_disguised_and_oversized_files_are_refused_without_side_effect(
        self, client: httpx.Client, operator: dict[str, str]
    ) -> None:
        created = _create(client, operator)
        path = f"{ADMIN}/{created['id']}/image"
        headers = {**operator, "Content-Type": "image/jpeg"}

        disguised = client.post(path, content=b"<?php echo 1; ?>", headers=headers)
        svg = client.post(path, content=b"<svg onload=alert(1)></svg>", headers=headers)
        big = client.post(path, content=JPEG + bytes(2 * 1024 * 1024), headers=headers)
        huge = client.post(path, content=bytes(4 * 1024 * 1024), headers=headers)

        assert (disguised.status_code, svg.status_code, big.status_code) == (422, 422, 422)
        assert huge.status_code == 413  # arrêté par la passerelle avant d'atteindre shop
        assert client.get(f"{ADMIN}/{created['id']}", headers=operator).json()["image_keys"] == []


class TestRateLimit:
    def test_a_burst_of_admin_requests_is_throttled_by_the_gateway(
        self, operator: dict[str, str]
    ) -> None:
        time.sleep(12)  # laisse la rafale des scénarios précédents se résorber
        plain = httpx.Client(base_url=BASE_URL, timeout=20.0)
        statuses = [plain.get(ADMIN, headers=operator).status_code for _ in range(70)]

        assert 429 in statuses
        assert statuses[0] == 200
