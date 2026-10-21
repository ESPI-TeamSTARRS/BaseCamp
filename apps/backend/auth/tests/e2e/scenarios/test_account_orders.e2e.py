"""Commandes rattachees au compte, de l'inscription a la liste, sur la pile reelle.

Traverse la passerelle Traefik, `auth` (inscription, verification par Mailpit, connexion) et `shop`
(commande, verification du jeton par JWKS, liste, rattachement). Les emails sont lus dans Mailpit
(`E2E_MAILPIT_URL`); le scenario « auth arrete » passe par `docker compose` (E2E_CHECK_LOGS=1).
"""

import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]  # docker compose se lance depuis la racine
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
MAILPIT_URL = os.environ.get("E2E_MAILPIT_URL", "")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
FILTER = "filtre-a-eau-portable"  # 34,00 EUR, gros stock
TOKEN_PATTERN = re.compile(r"/compte/verification#token=([A-Za-z0-9_-]+)")
MAIL_TIMEOUT_SECONDS = 15.0
ORDERS_RATE_PAUSE_SECONDS = 6.5  # /api/shop/orders : 10/min par IP a la passerelle
needs_mailbox = pytest.mark.skipif(not MAILPIT_URL, reason="definir E2E_MAILPIT_URL (Mailpit)")
needs_docker = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)


class Mailbox:
    def __init__(self) -> None:
        self._http = httpx.Client(base_url=MAILPIT_URL, timeout=5.0)

    def verification_token(self, address: str) -> str:
        deadline = time.monotonic() + MAIL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            found = self._http.get("/api/v1/search", params={"query": f"to:{address}"}).json()
            for item in found["messages"]:
                body = self._http.get(f"/api/v1/message/{item['ID']}").json()["Text"]
                match = TOKEN_PATTERN.search(body)
                if match:
                    return match.group(1)
            time.sleep(0.3)
        raise AssertionError("email de verification attendu, delai depasse")

    def purge(self, address: str) -> None:
        self._http.delete("/api/v1/search", params={"query": f"to:{address}"})


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as http:
        yield http


@pytest.fixture
def address() -> str:
    return f"e2e-compte-{uuid.uuid4().hex[:10]}@example.test"


def place_order(
    client: httpx.Client, email: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    body = {
        "email": email,
        "shippingAddress": {
            "fullName": "Client Compte",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": FILTER, "quantity": 1}],
    }
    request_headers = {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}", **(headers or {})}
    response = client.post("/api/shop/orders", json=body, headers=request_headers)
    for _ in range(8):
        if response.status_code != 429:
            break
        time.sleep(ORDERS_RATE_PAUSE_SECONDS)
        response = client.post("/api/shop/orders", json=body, headers=request_headers)
    assert response.status_code == 201, response.text
    return response


def register(client: httpx.Client, email: str) -> None:
    response = client.post("/api/auth/register", json={"email": email, "password": PHRASE})
    assert response.status_code == 202


def verify(client: httpx.Client, mailbox: Mailbox, email: str) -> None:
    token = mailbox.verification_token(email)
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200


def login(client: httpx.Client, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": PHRASE})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def my_orders(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/api/shop/me/orders", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


@needs_mailbox
class TestFromRegistrationToMyOrders:
    def test_register_verify_login_order_then_list_my_orders(
        self, client: httpx.Client, address: str
    ) -> None:
        mailbox = Mailbox()
        guest = place_order(client, address).json()  # commande invitee, AVANT le compte
        register(client, address)
        verify(client, mailbox, address)
        headers = login(client, address)

        connected = place_order(client, address, headers).json()
        orders = my_orders(client, headers)

        numbers = {item["number"] for item in orders["items"]}
        assert numbers == {guest["number"], connected["number"]}  # l'ancienne est rattachee
        assert orders["total"] == 2
        assert address not in str(orders)
        mailbox.purge(address)

    def test_an_unverified_email_gets_no_guest_order(
        self, client: httpx.Client, address: str
    ) -> None:
        place_order(client, address)
        register(client, address)  # jamais verifiee
        headers = login(client, address)

        assert my_orders(client, headers)["items"] == []

    def test_another_account_cannot_read_my_order_and_sees_the_same_404_as_for_an_unknown_one(
        self, client: httpx.Client, address: str
    ) -> None:
        mailbox = Mailbox()
        register(client, address)
        verify(client, mailbox, address)
        mine = login(client, address)
        order = place_order(client, address, mine).json()
        intruder_address = f"e2e-intrus-{uuid.uuid4().hex[:10]}@example.test"
        register(client, intruder_address)
        intruder = login(client, intruder_address)

        foreign = client.get(f"/api/shop/me/orders/{order['id']}", headers=intruder)
        unknown = client.get(f"/api/shop/me/orders/{uuid.uuid4()}", headers=intruder)
        own = client.get(f"/api/shop/me/orders/{order['id']}", headers=mine)

        assert foreign.status_code == unknown.status_code == 404
        assert foreign.content == unknown.content
        assert own.status_code == 200 and own.json()["number"] == order["number"]
        mailbox.purge(address)


class TestGuestJourneyIsUnchanged:
    def test_a_guest_can_still_buy_and_track_without_any_account(
        self, client: httpx.Client, address: str
    ) -> None:
        order = place_order(client, address).json()

        lookup = client.post(
            "/api/shop/orders/lookup", json={"orderNumber": order["number"], "email": address}
        )
        for _ in range(8):  # la passerelle limite aussi le suivi (meme seuil que les commandes)
            if lookup.status_code != 429:
                break
            time.sleep(ORDERS_RATE_PAUSE_SECONDS)
            lookup = client.post(
                "/api/shop/orders/lookup", json={"orderNumber": order["number"], "email": address}
            )

        assert lookup.status_code == 200
        assert lookup.json()["number"] == order["number"]

    def test_an_invalid_token_never_blocks_a_purchase(
        self, client: httpx.Client, address: str
    ) -> None:
        response = place_order(client, address, {"Authorization": "Bearer faux.jeton.x"})

        assert response.status_code == 201

    def test_the_account_routes_refuse_a_missing_or_forged_token(
        self, client: httpx.Client
    ) -> None:
        for headers in (None, {"Authorization": "Bearer faux.jeton.x"}):
            response = client.get("/api/shop/me/orders", headers=headers)

            assert response.status_code == 401
            assert response.json() == {"detail": "Authentification requise."}


def docker_compose(*arguments: str) -> None:
    subprocess.run(  # noqa: S603
        ["docker", "compose", *arguments],  # noqa: S607
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=True,
        cwd=REPO_ROOT,
    )


def wait_for_auth(client: httpx.Client) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if client.get("/api/auth/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise AssertionError("auth ne repond plus apres son redemarrage")


@needs_mailbox
@needs_docker
class TestAuthOutage:
    def test_tokens_already_issued_keep_working_while_the_auth_container_is_stopped(
        self, client: httpx.Client, address: str
    ) -> None:
        mailbox = Mailbox()
        register(client, address)
        verify(client, mailbox, address)
        headers = login(client, address)
        my_orders(client, headers)  # les cles de verification d'`auth` sont maintenant en cache
        docker_compose("stop", "auth")
        try:
            placed = place_order(client, address, headers).json()
            listing = client.get("/api/shop/me/orders", headers=headers)
        finally:
            docker_compose("start", "auth")
            wait_for_auth(client)

        assert listing.status_code == 200
        assert placed["number"] in {item["number"] for item in listing.json()["items"]}
        mailbox.purge(address)
