"""Aides des scénarios e2e shop <-> payment sur la pile réelle (pas un test).

Tout passe par la passerelle (`E2E_BASE_URL`) ou par `docker compose exec` dans les conteneurs : payment
n'est jamais joignable depuis l'hôte. `COMPOSE_FILE` est relatif à la racine du dépôt.
"""

import base64
import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
REPO_ROOT = Path(__file__).resolve().parents[5]
ORDERS_PATH = "/api/shop/orders"
PRODUCT = "boussole-orientation-pro"  # 29,00 EUR, gros stock
QUANTITY = 2
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8
DELIVERY_SECONDS = 40
LEDGER_CHECK = ["python", "-m", "app.ledgercheck.presentation.cli"]
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
# Prelude des scripts executes DANS le conteneur shop : obtient un vrai jeton de service aupres
# d'auth avec le secret de l'environnement du conteneur (il n'en sort jamais).
AUTH_CALL_PRELUDE = r"""
import json as _json, os as _os, urllib.request as _request


def service_token():
    body = _json.dumps({
        "grant_type": "client_credentials", "client_id": "shop",
        "client_secret": _os.environ["APP_AUTH_CLIENT_SECRET"],
        "audience": "payment", "scope": "payments:write",
    }).encode()
    issue = _request.Request("http://auth:8000/internal/token", data=body,
                             headers={"Content-Type": "application/json"}, method="POST")
    return _json.load(_request.urlopen(issue, timeout=10))["access_token"]
"""
_operator: list[str] = []

needs_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="docker compose requis (conteneur shop)"
)


def new_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15.0)


def post(client: httpx.Client, path: str, body: Any, headers: dict[str, str] | None = None) -> Any:
    """POST ; sur 429 de la passerelle on patiente puis on rejoue (les routes sont idempotentes)."""
    response = client.post(path, json=body, headers=headers)
    for _ in range(RATE_LIMIT_ATTEMPTS):
        if response.status_code != 429:
            break
        time.sleep(RATE_LIMIT_PAUSE_SECONDS)
        response = client.post(path, json=body, headers=headers)
    return response


def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - commande fixe, arguments des tests uniquement
        ["docker", "compose", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=REPO_ROOT,
    )


def compose(*args: str) -> str:
    result = run(*args)
    assert result.returncode == 0, result.stderr[-300:]
    return result.stdout


def shop_psql(sql: str) -> str:
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "shop", "-At", "-c", sql
    ).strip()


def in_shop(script: str, *args: str) -> dict[str, Any]:
    """Exécute un script Python DANS le conteneur shop; sa dernière ligne est un JSON."""
    output = compose("exec", "-T", "shop", "python", "-c", script, *args)
    return dict(json.loads(output.strip().splitlines()[-1]))


# Execute dans le conteneur auth : enrole le gabarit facial (FAUX verificateur de developpement).
_ENROLL = """
import base64, sys
from datetime import UTC, datetime
from sqlalchemy import create_engine, text
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import FakeReconnaissanceFaciale
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.backoffice.infrastructure.clients.face_template_key_file import load_template_cipher
from app.core.config import Settings

engine = create_engine(Settings().database_url)
with engine.connect() as connection:
    account = connection.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": sys.argv[1]}
    ).scalar_one()
template = FakeReconnaissanceFaciale().enroler([base64.b64decode(sys.argv[2])])
cipher = load_template_cipher(Settings().face_template_key_file)
with SqlAlchemyBackofficeUnitOfWork(engine, cipher) as work:
    work.templates.save(account, template, datetime.now(UTC))
    work.commit()
"""
FACE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"visage-de-l-operateur-e2e").decode()


def operator_token() -> str:
    """Jeton d'un operateur reel, par la connexion du back-office en trois temps (identifiant, visage,
    mot de passe) sur l'origine du back-office : le login classique ne delivre plus le role `operator`."""
    if _operator:
        return _operator[0]
    email = f"e2e-operator-{uuid.uuid4().hex[:10]}@example.test"
    created = run(
        *["exec", "-T", "-e", f"OPERATOR_PASSWORD={PHRASE}", "auth"],
        *["python", "-m", "app.admin.create_operator", "--email", email],
        timeout=180,
    )
    assert created.returncode == 0, created.stderr[-300:]
    compose("exec", "-T", "auth", "python", "-c", _ENROLL, email, FACE)
    with httpx.Client(
        base_url=BASE_URL, timeout=30.0, headers={"Host": "mercure.localhost"}
    ) as admin:
        identified = admin.post("/api/auth/backoffice/identify", json={"email": email})
        assert identified.status_code == 200, identified.status_code
        challenge = identified.json()["challenge_id"]
        shown = admin.post(
            "/api/auth/backoffice/face", json={"challenge_id": challenge, "images": [FACE]}
        )
        assert shown.status_code == 200, shown.status_code
        response = admin.post(
            "/api/auth/backoffice/password", json={"challenge_id": challenge, "password": PHRASE}
        )
    assert response.status_code == 200, response.status_code
    _operator.append(str(response.json()["access_token"]))
    return _operator[0]


def wait_for(check: Callable[[], Any], message: str) -> Any:
    deadline = time.monotonic() + DELIVERY_SECONDS
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(1.0)
    pytest.fail(message)


def place_order(client: httpx.Client, email_prefix: str) -> tuple[dict[str, Any], str]:
    """Crée une commande par la passerelle; renvoie sa représentation et l'email utilisé."""
    email = f"{email_prefix}.{uuid.uuid4().hex[:12]}@example.org"
    body = {
        "email": email,
        "shippingAddress": {
            "fullName": "Client E2E",
            "line1": "1 rue du Test",
            "postalCode": "75001",
            "city": "Paris",
            "country": "FR",
        },
        "lines": [{"productId": PRODUCT, "quantity": QUANTITY}],
    }
    order = post(client, ORDERS_PATH, body, {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})
    assert order.status_code == 201
    return dict(order.json()), email
