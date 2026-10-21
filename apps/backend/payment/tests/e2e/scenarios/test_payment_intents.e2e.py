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


# --- Confirmation et grand livre -------------------------------------------------------------

CONCURRENT_SCRIPT = """
import json, sys, threading, urllib.request, urllib.error
path, token, same_key, count, body = sys.argv[1:6]
barrier, results = threading.Barrier(int(count)), []

def attempt(index):
    key = "e2e-conc-" + (path[-40:-4] if same_key == "1" else path[-40:-4] + str(index))
    request = urllib.request.Request(
        "http://payment:8000" + path, data=body.encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token,
                 "Idempotency-Key": key},
    )
    barrier.wait()
    try:
        results.append(urllib.request.urlopen(request, timeout=10).status)
    except urllib.error.HTTPError as error:
        results.append(error.code)

threads = [threading.Thread(target=attempt, args=(i,)) for i in range(int(count))]
[t.start() for t in threads]
[t.join() for t in threads]
print(json.dumps(sorted(results)))
"""
CARD_NUMBER = "4242424242424242"


def _psql(sql: str) -> subprocess.CompletedProcess[str]:
    """Exécute du SQL dans payment-db (le seul compte est le propriétaire de la base)."""
    command = ["docker", "compose", "exec", "-T", "payment-db", "sh", "-c"]
    command.append('psql -v ON_ERROR_STOP=1 -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"')
    command.append(sql)
    return subprocess.run(  # noqa: S603
        command, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=60
    )


def _ledger_rows(intent_id: object) -> list[str]:
    result = _psql(
        "SELECT account || '|' || direction || '|' || amount FROM ledger_entries "
        f"WHERE intent_id = '{uuid.UUID(str(intent_id))}' ORDER BY direction"
    )
    return result.stdout.split()


def _confirm(
    token: str, intent_id: object, method: object, key: str
) -> tuple[int, dict[str, object]]:
    return _call(
        "POST",
        f"/payments/intents/{intent_id}/confirm",
        token=token,
        key=key,
        body={"payment_method": method},
    )


def _new_intent(token: str) -> str:
    _, created = _call(
        "POST", "/payments/intents", token=token, key=f"e2e-{uuid.uuid4().hex}", body=_order()
    )
    return str(created["id"])


class TestConfirmation:
    def test_success_writes_two_balanced_ledger_entries(self, token: str) -> None:
        intent_id, key = _new_intent(token), f"e2e-{uuid.uuid4().hex}"

        status, confirmed = _confirm(token, intent_id, "pm_test_success", key)
        replay_status, replay = _confirm(token, intent_id, "pm_test_success", key)
        other_key, _ = _confirm(token, intent_id, "pm_test_success", f"e2e-{uuid.uuid4().hex}")
        _, read = _call("GET", f"/payments/intents/{intent_id}", token=token)

        assert (status, confirmed["status"]) == (200, "succeeded")
        assert (replay_status, replay) == (200, confirmed)
        assert other_key == 409
        assert read["status"] == "succeeded"
        assert _ledger_rows(intent_id) == ["marchand|credit|4990", "client_attente|debit|4990"]

    @pytest.mark.parametrize("method", ["pm_test_declined", "pm_test_timeout"])
    def test_decline_and_timeout_fail_the_intent_without_ledger_entries(
        self, token: str, method: str
    ) -> None:
        intent_id = _new_intent(token)

        status, confirmed = _confirm(token, intent_id, method, f"e2e-{uuid.uuid4().hex}")

        assert (status, confirmed["status"]) == (200, "failed")
        assert _ledger_rows(intent_id) == []

    def test_a_card_number_is_a_422_and_is_never_logged(self, token: str) -> None:
        intent_id = _new_intent(token)

        status, body = _confirm(token, intent_id, CARD_NUMBER, f"e2e-{uuid.uuid4().hex}")
        logs = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "payment"],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )

        assert status == 422
        assert CARD_NUMBER not in json.dumps(body)
        assert CARD_NUMBER not in logs.stdout + logs.stderr
        assert _ledger_rows(intent_id) == []

    def test_concurrent_confirmations_of_one_intent_only_one_succeeds(self, token: str) -> None:
        intent_id = _new_intent(token)
        path = f"/payments/intents/{intent_id}/confirm"

        command = ["docker", "compose", "exec", "-T", "shop", "python", "-c", CONCURRENT_SCRIPT]
        command += [path, token, "0", "5", json.dumps({"payment_method": "pm_test_success"})]
        output = subprocess.run(  # noqa: S603
            command, cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=60
        ).stdout

        assert json.loads(output.strip().splitlines()[-1]) == [200, 409, 409, 409, 409]
        assert len(_ledger_rows(intent_id)) == 2

    def test_ledger_lines_cannot_be_changed_or_unbalanced(self, token: str) -> None:
        intent_id = _new_intent(token)
        _confirm(token, intent_id, "pm_test_success", f"e2e-{uuid.uuid4().hex}")
        where = f"WHERE intent_id = '{intent_id}'"

        update = _psql(f"UPDATE ledger_entries SET amount = 1 {where}")
        delete = _psql(f"DELETE FROM ledger_entries {where}")
        unbalanced = _psql(
            "INSERT INTO ledger_entries (id, transaction_id, intent_id, account, direction, "
            f"amount, created_at) VALUES (gen_random_uuid(), gen_random_uuid(), '{intent_id}', "
            "'client_attente', 'debit', 10, now())"
        )

        assert update.returncode != 0
        assert "ajout seul" in update.stderr
        assert delete.returncode != 0
        assert "ajout seul" in delete.stderr
        assert unbalanced.returncode != 0
        assert "desequilibree" in unbalanced.stderr
        assert _ledger_rows(intent_id) == ["marchand|credit|4990", "client_attente|debit|4990"]
