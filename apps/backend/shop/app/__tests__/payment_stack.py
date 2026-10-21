"""Aides des scénarios e2e shop <-> payment sur la pile réelle (pas un test).

Tout passe par la passerelle (`E2E_BASE_URL`) ou par `docker compose exec` dans les conteneurs : payment
n'est jamais joignable depuis l'hôte. `COMPOSE_FILE` est relatif à la racine du dépôt.
"""

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
