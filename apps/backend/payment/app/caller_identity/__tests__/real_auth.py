"""Vrais jetons d'`auth` pour les scenarios e2e (pile docker compose lancee, aucun jeton statique).

- Jeton de SERVICE : demande a `auth` (`POST /internal/token`, reseau interne) depuis le conteneur
  `shop`, comme le fait la boutique; le secret du client `shop` vient de l'environnement ou du `.env`.
- Jeton OPERATEUR : l'operateur est cree par la commande d'exploitation `create-operator`, puis se
  connecte par la passerelle (`/api/auth/login`), comme un vrai back-office.
- Jeton CLIENT : un compte client inscrit puis connecte par la passerelle.
Les jetons sont gardes un court moment (ils vivent 5 minutes) pour ne pas solliciter `auth` a chaque appel.
"""

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[6]
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
SHOP_SECRET_VARIABLE = "AUTH_SERVICE_CLIENT_" + "SECRET_SHOP"  # nom de variable, pas une valeur
CACHE_SECONDS = 120
PHRASE = "Randonnee-GR20-" + uuid.uuid4().hex[:12]
# Execute dans le conteneur shop : un POST JSON vers auth, la reponse est imprimee en JSON.
_ISSUE_SCRIPT = """
import json, sys, urllib.request, urllib.error
body = json.dumps({"grant_type": "client_credentials", "client_id": "shop", "client_secret": sys.argv[1],
                   "audience": "payment", "scope": sys.argv[2]}).encode()
request = urllib.request.Request("http://auth:8000/internal/token", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
try:
    print(json.dumps({"status": 200, "body": json.load(urllib.request.urlopen(request, timeout=10))}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "body": None}))
"""
_cache: dict[str, tuple[float, str]] = {}


def env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{name} introuvable")


def _cached(key: str, make: Callable[[], str]) -> str:
    stored = _cache.get(key)
    if stored is not None and time.monotonic() - stored[0] < CACHE_SECONDS:
        return stored[1]
    token: str = make()
    _cache[key] = (time.monotonic(), token)
    return token


def service_token(scope: str = "payments:write") -> str:
    """Jeton de service de `shop` (audience payment) emis par la vraie `auth`."""

    def issue() -> str:
        command = ["docker", "compose", "exec", "-T", "shop", "python", "-c", _ISSUE_SCRIPT]
        command += [env_value(SHOP_SECRET_VARIABLE), scope]
        output = subprocess.run(  # noqa: S603 - commande fixe, arguments maitrises par le test
            command, cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=60
        ).stdout
        result = json.loads(output.strip().splitlines()[-1])
        assert result["status"] == 200, f"auth a refuse le jeton de service ({result['status']})"
        return str(result["body"]["access_token"])

    return _cached(f"service:{scope}", issue)


def _login(email: str) -> str:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        response = client.post("/api/auth/login", json={"email": email, "password": PHRASE})
    assert response.status_code == 200, response.status_code
    return str(response.json()["access_token"])


def operator_token() -> str:
    """Jeton client d'un operateur cree par `create-operator`, puis connecte par la passerelle."""

    def make() -> str:
        email = f"e2e-operator-{uuid.uuid4().hex[:10]}@example.test"
        command = ["docker", "compose", "exec", "-T", "-e", f"OPERATOR_PASSWORD={PHRASE}", "auth"]
        command += ["python", "-m", "app.admin.create_operator", "--email", email]
        created = subprocess.run(  # noqa: S603
            command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180, check=False
        )
        assert created.returncode == 0, created.stderr
        return _login(email)

    return _cached("operator", make)


def customer_token() -> str:
    """Jeton client d'un compte client ordinaire (sans role operateur)."""

    def make() -> str:
        email = f"e2e-customer-{uuid.uuid4().hex[:10]}@example.test"
        with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
            registered = client.post(
                "/api/auth/register", json={"email": email, "password": PHRASE}
            )
        assert registered.status_code == 202, registered.status_code
        return _login(email)

    return _cached("customer", make)
