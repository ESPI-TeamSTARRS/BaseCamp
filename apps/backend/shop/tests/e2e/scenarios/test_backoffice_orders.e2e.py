"""Commandes consultées depuis le back-office sur la pile : routes serveur (/bff), shop, passerelle et site client.

Une commande passée sur le site client (POST /api/shop/orders) doit apparaître côté back-office avec le bon
statut et son détail, en lecture seule. Le jeton d'opérateur est signé avec la clé de développement d'`auth`
(comme dans `test_backoffice_catalog`) ; le navigateur n'a que son cookie de session. Les requêtes du
back-office portent `Host: mercure.localhost` ; le site client est appelé sur le domaine principal.
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
ADMIN_HOST = {"Host": "mercure.localhost"}
SAME_ORIGIN = {**ADMIN_HOST, "Sec-Fetch-Site": "same-origin"}
BFF = "/bff/orders"
ADMIN_API = "/api/shop/admin/orders"
ORDERS_PATH = "/api/shop/orders"
FILTER = "filtre-a-eau-portable"  # 34,00 EUR, gros stock
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min
RATE_LIMIT_ATTEMPTS = 8


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


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"bo_access={token}"}


class PatientClient(httpx.Client):
    """Patiente quand la passerelle limite le débit."""

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        response = super().send(request, **kwargs)
        for _ in range(RATE_LIMIT_ATTEMPTS):
            if response.status_code != 429:
                break
            time.sleep(RATE_LIMIT_PAUSE_SECONDS)
            response = super().send(request, **kwargs)
        return response


@pytest.fixture(scope="module")
def session() -> dict[str, str]:
    return {**SAME_ORIGIN, **_cookie(_token(["operator"], ["pwd", "face"]))}


@pytest.fixture
def client() -> Any:
    with PatientClient(base_url=BASE_URL, timeout=30.0, follow_redirects=False) as session:
        yield session


def _place_order(client: httpx.Client) -> dict[str, Any]:
    """Une commande passée sur le site client, par un invité (adresse unique pour la retrouver)."""
    email = f"e2e.bo.{uuid.uuid4().hex[:10]}@example.org"
    body = {
        "email": email,
        "shippingAddress": {
            "fullName": "Client BO E2E",
            "line1": "1 rue du Test",
            "line2": "Bâtiment C",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": FILTER, "quantity": 2}],
    }
    response = client.post(
        ORDERS_PATH, json=body, headers={"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"}
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "email": email}


class TestGuard:
    def test_the_order_screens_and_routes_need_a_session(self, client: httpx.Client) -> None:
        for path in ("/commandes", "/commandes/00000000-0000-4000-8000-000000000001"):
            response = client.get(path, headers=ADMIN_HOST)
            assert response.status_code == 307, path
            assert response.headers["location"].endswith("/login"), path
        for path in (BFF, f"{BFF}/00000000-0000-4000-8000-000000000001"):
            response = client.get(path, headers=SAME_ORIGIN)
            assert (response.status_code, response.json()["detail"]) == (
                401,
                "Authentification requise.",
            ), path

    def test_a_token_without_the_face_factor_or_a_customer_token_opens_nothing(
        self, client: httpx.Client
    ) -> None:
        for roles, amr in ((["operator"], ["pwd"]), (["customer"], ["pwd", "face"])):
            headers = {**SAME_ORIGIN, **_cookie(_token(roles, amr))}

            assert client.get(BFF, headers=headers).status_code == 401
            assert client.get("/commandes", headers=headers).status_code == 307

    def test_the_shop_api_refuses_a_customer_or_a_single_factor_operator(
        self, client: httpx.Client
    ) -> None:
        customer = {
            **ADMIN_HOST,
            "Authorization": f"Bearer {_token(['customer'], ['pwd', 'face'])}",
        }
        no_face = {**ADMIN_HOST, "Authorization": f"Bearer {_token(['operator'], ['pwd'])}"}

        assert client.get(ADMIN_API, headers=ADMIN_HOST).status_code == 401
        assert client.get(ADMIN_API, headers=customer).status_code == 403
        assert client.get(ADMIN_API, headers=no_face).status_code == 403

    def test_the_order_api_answers_only_on_the_admin_origin(self, client: httpx.Client) -> None:
        token = _token(["operator"], ["pwd", "face"])

        on_main = client.get(ADMIN_API, headers={"Authorization": f"Bearer {token}"})

        assert on_main.status_code == 404
        assert "application/json" not in on_main.headers.get("content-type", "")

    def test_nothing_can_be_written_through_the_order_routes(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            assert client.request(method, BFF, headers=session).status_code == 405, method


class TestOrdersFromTheBackOffice:
    def test_an_order_placed_on_the_site_is_visible_with_its_status_and_detail(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        placed = _place_order(client)

        listed = client.get(f"{BFF}?q={placed['number']}", headers=session)

        assert listed.status_code == 200
        assert listed.headers["cache-control"] == "no-store"
        (found,) = listed.json()["items"]
        assert (found["id"], found["number"]) == (placed["id"], placed["number"])
        assert found["status"] == "pending_payment"
        assert found["email"] == placed["email"]
        assert found["total_cents"] == placed["total_cents"] and found["item_count"] == 2
        detail = client.get(f"{BFF}/{placed['id']}", headers=session)
        assert detail.status_code == 200
        order = detail.json()
        assert order["status"] == "pending_payment"
        assert order["shipping_address"] == {
            "full_name": "Client BO E2E",
            "line1": "1 rue du Test",
            "line2": "Bâtiment C",
            "postal_code": "75001",
            "city": "Paris",
            "country": "FR",
        }
        assert [(line["quantity"], line["unit_price_cents"]) for line in order["lines"]] == [
            (2, 3400)
        ]
        assert order["subtotal_cents"] + order["shipping_cents"] == order["total_cents"]

    def test_the_list_filters_by_status_and_searches_by_email(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        placed = _place_order(client)

        by_email = client.get(f"{BFF}?q={placed['email']}&status=pending_payment", headers=session)
        wrong_status = client.get(f"{BFF}?q={placed['number']}&status=refunded", headers=session)
        latest = client.get(f"{BFF}?limit=20", headers=session).json()

        assert [o["id"] for o in by_email.json()["items"]] == [placed["id"]]
        assert wrong_status.json()["total"] == 0
        assert latest["limit"] == 20 and len(latest["items"]) <= 20
        dates = [o["created_at"] for o in latest["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_a_malformed_query_and_an_unknown_order_are_refused_with_fixed_messages(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        bad = client.get(f"{BFF}?status=shipped", headers=session)
        unknown = client.get(f"{BFF}/{uuid.uuid4()}", headers=session)

        assert (bad.status_code, bad.json()["code"]) == (400, "bad_request")
        assert (unknown.status_code, unknown.json()) == (
            404,
            {"detail": "Commande introuvable.", "code": "not_found"},
        )

    def test_the_screens_are_served_with_a_session(
        self, client: httpx.Client, session: dict[str, str]
    ) -> None:
        placed = _place_order(client)

        for path, text in (
            ("/commandes", "Commandes"),
            (f"/commandes/{placed['id']}", "Détail de la commande"),
        ):
            response = client.get(path, headers=session)
            assert response.status_code == 200 and text in response.text, path
