"""Administration des comptes sur la pile reelle : Traefik, auth et Postgres.

L'operateur est cree par la commande d'exploitation `create-operator` dans le conteneur `auth`
(`docker compose exec`, E2E_CHECK_LOGS=1) : aucune route HTTP ne cree ce role.
"""

import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from app.backoffice.__tests__.real_stack import enroll_face, operator_bearer

REPO_ROOT = Path(__file__).resolve().parents[6]  # docker compose se lance depuis la racine
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
pytestmark = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as http:
        yield http


def create_operator(email: str) -> subprocess.CompletedProcess[str]:
    command = ["docker", "compose", "exec", "-T", "-e", f"OPERATOR_PASSWORD={PHRASE}", "auth"]
    command += ["python", "-m", "app.admin.create_operator", "--email", email]
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
        cwd=REPO_ROOT,
    )


def register(client: httpx.Client, email: str) -> None:
    assert (
        client.post("/api/auth/register", json={"email": email, "password": PHRASE}).status_code
        == 202
    )


def bearer(client: httpx.Client, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": PHRASE})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def operator(client: httpx.Client) -> str:
    email = f"e2e-operator-{uuid.uuid4().hex[:10]}@example.test"
    created = create_operator(email)
    assert created.returncode == 0, created.stderr
    enroll_face(email)  # la connexion du back-office passe par le visage (WORK-59)
    return email


def test_the_command_creates_an_operator_and_refuses_a_duplicate(operator: str) -> None:
    again = create_operator(operator)

    assert again.returncode == 1
    assert "existe déjà" in again.stderr
    assert PHRASE not in again.stdout + again.stderr


def test_without_a_token_401_and_with_a_customer_token_403(client: httpx.Client) -> None:
    customer = f"e2e-customer-{uuid.uuid4().hex[:10]}@example.test"
    register(client, customer)

    assert client.get("/api/auth/admin/users").status_code == 401
    forbidden = client.get("/api/auth/admin/users", headers=bearer(client, customer))
    assert (forbidden.status_code, forbidden.json()) == (403, {"detail": "Accès refusé."})


def test_an_operator_lists_and_disables_an_account(client: httpx.Client, operator: str) -> None:
    customer = f"e2e-target-{uuid.uuid4().hex[:10]}@example.test"
    register(client, customer)
    headers = operator_bearer(operator, PHRASE)

    listing = client.get("/api/auth/admin/users?limit=100", headers=headers)
    assert listing.status_code == 200
    target = next(item for item in listing.json()["items"] if item["email"] == customer)
    assert target["role"] == "customer"

    disabled = client.post(f"/api/auth/admin/users/{target['id']}/disable", headers=headers)
    refused = client.post("/api/auth/login", json={"email": customer, "password": PHRASE})
    enabled = client.post(f"/api/auth/admin/users/{target['id']}/enable", headers=headers)

    assert disabled.status_code == 200 and disabled.json()["disabled"] is True
    assert (refused.status_code, refused.json()) == (401, {"detail": "Identifiants invalides."})
    assert enabled.status_code == 200 and enabled.json()["disabled"] is False
    assert (
        client.post("/api/auth/login", json={"email": customer, "password": PHRASE}).status_code
        == 200
    )


def test_an_operator_cannot_disable_themselves(client: httpx.Client, operator: str) -> None:
    headers = operator_bearer(operator, PHRASE)
    me = client.get("/api/auth/me", headers=headers).json()

    response = client.post(f"/api/auth/admin/users/{me['id']}/disable", headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "cannot_disable_self"


def test_the_public_registration_never_grants_a_role(client: httpx.Client) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"e2e-pirate-{uuid.uuid4().hex[:8]}@example.test",
            "password": PHRASE,
            "role": "operator",
        },
    )

    assert response.status_code == 422
