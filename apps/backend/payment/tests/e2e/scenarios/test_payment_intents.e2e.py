"""Parcours d'intention de paiement sur la pile : appels faits depuis `shop`, le seul appelant.

payment n'est pas joignable depuis l'hôte : on exécute donc les requêtes dans le conteneur shop
(`docker compose exec`). Le jeton vient de PAYMENT_SERVICE_TOKEN_SHOP (environnement ou .env).
"""

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]
SCRIPT = """
import json, sys, urllib.request, urllib.error
method, path, token, key, body = sys.argv[1:6]
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = "Bearer " + token
if key:
    headers["Idempotency-Key"] = key
request = urllib.request.Request(
    "http://payment:8000" + path, data=body.encode() if body else None, headers=headers, method=method
)
try:
    response = urllib.request.urlopen(request, timeout=5)
    print(json.dumps({"status": response.status, "body": json.load(response)}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "body": json.loads(error.read() or "null")}))
"""


def _service_token() -> str:
    token = os.environ.get("PAYMENT_SERVICE_TOKEN_SHOP")
    if token:
        return token
    for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("PAYMENT_SERVICE_TOKEN_SHOP="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("PAYMENT_SERVICE_TOKEN_SHOP introuvable")


def _call(
    method: str,
    path: str,
    *,
    token: str | None,
    key: str = "",
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    command = ["docker", "compose", "exec", "-T", "shop", "python", "-c", SCRIPT]
    command += [method, path, token or "", key, json.dumps(body) if body else ""]
    output = subprocess.run(  # noqa: S603
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=60
    ).stdout
    result = json.loads(output.strip().splitlines()[-1])
    return result["status"], result["body"]


@pytest.fixture
def token() -> str:
    return _service_token()


def _order() -> dict[str, object]:
    return {"order_reference": f"E2E-{uuid.uuid4().hex[:12]}", "amount": 4990, "currency": "EUR"}


class TestPaymentIntents:
    def test_create_replay_and_read_an_intent(self, token: str) -> None:
        body, key = _order(), f"e2e-{uuid.uuid4().hex}"

        status, created = _call("POST", "/payments/intents", token=token, key=key, body=body)
        replay_status, replay = _call("POST", "/payments/intents", token=token, key=key, body=body)
        read_status, read = _call("GET", f"/payments/intents/{created['id']}", token=token)

        assert status == 201
        assert created["status"] == "requires_confirmation"
        assert (replay_status, replay["id"]) == (200, created["id"])
        assert (read_status, read["amount"], read["refunded_amount"]) == (200, 4990, 0)

    def test_rules_on_keys_and_orders(self, token: str) -> None:
        body, key = _order(), f"e2e-{uuid.uuid4().hex}"
        _call("POST", "/payments/intents", token=token, key=key, body=body)

        changed, _ = _call(
            "POST", "/payments/intents", token=token, key=key, body={**body, "amount": 1}
        )
        duplicate, _ = _call(
            "POST", "/payments/intents", token=token, key=f"e2e-{uuid.uuid4().hex}", body=body
        )
        by_order, found = _call(
            "GET", f"/payments/intents?order_reference={body['order_reference']}", token=token
        )

        assert changed == 422
        assert duplicate == 409
        assert (by_order, found["order_reference"]) == (200, body["order_reference"])

    def test_invalid_amounts_are_rejected(self, token: str) -> None:
        for amount in (0, -1, 500_001):
            status, _ = _call(
                "POST",
                "/payments/intents",
                token=token,
                key=f"e2e-{uuid.uuid4().hex}",
                body={**_order(), "amount": amount},
            )
            assert status == 422

    def test_missing_or_wrong_token_gets_the_same_401(self, token: str) -> None:
        missing = _call("POST", "/payments/intents", token=None, key="e2e-key-0001", body=_order())
        wrong = _call("POST", "/payments/intents", token="wrong", key="e2e-key-0001", body=_order())

        assert missing == wrong
        assert missing[0] == 401

    def test_unknown_intent_is_a_generic_404(self, token: str) -> None:
        status, body = _call("GET", f"/payments/intents/{uuid.uuid4()}", token=token)

        assert (status, body) == (404, {"detail": "Not found"})
