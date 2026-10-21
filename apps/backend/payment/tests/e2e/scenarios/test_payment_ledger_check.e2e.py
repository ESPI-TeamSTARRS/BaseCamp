"""Contrôle du grand livre sur la pile (WORK-26) : `ledger-check` lancé dans le conteneur `payment`.

L'état est produit par l'API réelle depuis le conteneur `shop` (création, confirmation, remboursement),
puis la commande est exécutée comme le ferait un planificateur : `docker compose exec`. Sur un état
sain elle répond « cohérent » et sort en 0; elle n'écrit rien; ses lignes de journal suivent le schéma.
"""

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.caller_identity.__tests__.real_auth import operator_token, service_token

REPO_ROOT = Path(__file__).resolve().parents[6]
SCHEMA = json.loads(
    (REPO_ROOT / "docs/development/log-event.schema.json").read_text(encoding="utf-8")
)
COMMAND = ["python", "-m", "app.ledgercheck.presentation.cli"]

CALL_SCRIPT = """
import json, sys, urllib.request, urllib.error
method, path, token, key, body = sys.argv[1:6]
headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token}
if key:
    headers["Idempotency-Key"] = key
request = urllib.request.Request(
    "http://payment:8000" + path, data=body.encode() if body else None, headers=headers, method=method
)
try:
    response = urllib.request.urlopen(request, timeout=10)
    print(json.dumps({"status": response.status, "body": json.load(response)}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "body": json.loads(error.read() or "null")}))
"""


def _compose(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["docker", "compose", *args],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
    )


def _env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{name} introuvable")


def _call(method: str, path: str, key: str = "", body: dict[str, object] | None = None) -> Any:
    result = _compose(
        *["exec", "-T", "shop", "python", "-c", CALL_SCRIPT],
        method,
        path,
        operator_token() if path.endswith("/refunds") else service_token(),
        key,
        json.dumps(body) if body is not None else "",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _paid_and_refunded(refund: int) -> str:
    created = _call(
        "POST",
        "/payments/intents",
        f"e2e-{uuid.uuid4().hex}",
        {"order_reference": f"E2E-{uuid.uuid4().hex[:12]}", "amount": 10000, "currency": "EUR"},
    )
    assert created["status"] == 201
    intent_id = str(created["body"]["id"])
    confirmed = _call(
        "POST",
        f"/payments/intents/{intent_id}/confirm",
        f"e2e-{uuid.uuid4().hex}",
        {"payment_method": "pm_test_success"},
    )
    assert confirmed["status"] == 200
    refunded = _call(
        "POST",
        f"/payments/intents/{intent_id}/refunds",
        f"e2e-refund-{uuid.uuid4().hex}",
        {"amount": refund},
    )
    assert refunded["status"] == 201
    return intent_id


def _ledger_check() -> subprocess.CompletedProcess[str]:
    return _compose("exec", "-T", "payment", *COMMAND, timeout=60)


def _psql_scalar(sql: str) -> str:
    result = _compose(
        "exec",
        "-T",
        "payment-db",
        "sh",
        "-c",
        'psql -v ON_ERROR_STOP=1 -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"',
        sql,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestLedgerCheckOnTheStack:
    def test_a_healthy_state_after_a_confirmation_and_a_refund_is_coherent(self) -> None:
        _paid_and_refunded(4000)

        result = _ledger_check()

        assert result.returncode == 0, result.stdout + result.stderr
        lines = result.stdout.splitlines()
        assert "grand livre cohérent" in lines
        assert "écarts : 0" in lines
        assert any(line.startswith("débits : ") for line in lines)
        assert any(line.startswith("crédits : ") for line in lines)

    def test_the_command_writes_nothing_to_the_ledger(self) -> None:
        _paid_and_refunded(1000)
        count = "SELECT count(*) FROM ledger_entries"
        before = _psql_scalar(count)

        assert _ledger_check().returncode == 0

        assert _psql_scalar(count) == before

    def test_the_summary_line_follows_the_common_schema_without_any_secret(self) -> None:
        _paid_and_refunded(2500)

        result = _ledger_check()

        records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        (summary,) = records
        assert not list(Draft202012Validator(SCHEMA).iter_errors(summary)), summary
        assert (summary["event"], summary["outcome"]) == ("ledger.check_completed", "success")
        assert service_token() not in result.stdout + result.stderr
