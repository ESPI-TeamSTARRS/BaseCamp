"""Verrouillage progressif sur la pile reelle : l'etat est en base (Postgres), pas en memoire.

Le nom place ce fichier apres les autres scenarios d'auth (et avant `test_zz_gateway_protection`) :
`login` et `register` partagent un seuil par IP a la passerelle (60/min, rafale 30), que ces
scenarios consomment.
"""

import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
GENERIC = {"detail": "Identifiants invalides."}


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture
def address(client: httpx.Client) -> str:
    email = f"e2e-lock-{uuid.uuid4().hex[:10]}@example.test"
    assert (
        client.post("/api/auth/register", json={"email": email, "password": PHRASE}).status_code
        == 202
    )
    return email


def login(client: httpx.Client, email: str, password: str) -> httpx.Response:
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_five_failures_lock_the_account_even_for_the_right_password(
    client: httpx.Client, address: str
) -> None:
    for _ in range(5):
        assert login(client, address, "mauvais-mot-de-passe").status_code == 401

    locked = login(client, address, PHRASE)

    assert locked.status_code == 401
    assert locked.json() == GENERIC
    assert "set-cookie" not in locked.headers


def test_an_unknown_address_is_locked_exactly_like_a_known_one(client: httpx.Client) -> None:
    email = f"e2e-nobody-{uuid.uuid4().hex[:10]}@example.test"
    for _ in range(5):
        login(client, email, "mauvais-mot-de-passe")

    response = login(client, email, PHRASE)

    assert (response.status_code, response.json()) == (401, GENERIC)


def test_a_success_resets_the_counter(client: httpx.Client, address: str) -> None:
    for _ in range(4):
        login(client, address, "mauvais-mot-de-passe")
    assert login(client, address, PHRASE).status_code == 200

    for _ in range(4):
        login(client, address, "mauvais-mot-de-passe")

    assert login(client, address, PHRASE).status_code == 200
