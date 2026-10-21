"""Remboursement sur la pile (WORK-24), depuis le conteneur `shop` comme le vrai appelant.

Vérifie l'API, l'idempotence, le plafond « somme des remboursements <= montant capturé » (y compris
sous concurrence entre les deux instances de `payment` et directement en SQL), les écritures de
grand livre inverses, l'événement de l'outbox et la propreté du journal.
"""

import json
import os
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[6]
SCHEMA = json.loads(
    (REPO_ROOT / "docs/development/log-event.schema.json").read_text(encoding="utf-8")
)
CAPTURED = 10000

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

# Plusieurs remboursements lancés au même instant (une barrière), pour viser les deux instances.
PARALLEL_SCRIPT = """
import json, sys, threading, urllib.request, urllib.error
path, token, amount, count, prefix = sys.argv[1:6]
barrier = threading.Barrier(int(count))
results = []

def attempt(n):
    request = urllib.request.Request(
        "http://payment:8000" + path,
        data=json.dumps({"amount": int(amount)}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "Idempotency-Key": prefix + str(n),
        },
        method="POST",
    )
    barrier.wait()
    try:
        results.append(urllib.request.urlopen(request, timeout=20).status)
    except urllib.error.HTTPError as error:
        results.append(error.code)

threads = [threading.Thread(target=attempt, args=(n,)) for n in range(int(count))]
for thread in threads:
    thread.start()
for thread in threads:
    thread.join()
print(json.dumps(sorted(results)))
"""


def _compose(
    *args: str, timeout: int = 120, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["docker", "compose", *args],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
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


def _call(
    method: str, path: str, *, key: str = "", body: Mapping[str, object] | None = None
) -> tuple[int, Any]:
    output = _compose(
        *["exec", "-T", "shop", "python", "-c", CALL_SCRIPT],
        method,
        path,
        _env_value("PAYMENT_SERVICE_TOKEN_SHOP"),
        key,
        json.dumps(body) if body is not None else "",
        timeout=60,
    ).stdout
    result = json.loads(output.strip().splitlines()[-1])
    return result["status"], result["body"]


def _psql(sql: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["exec", "-T", "payment-db", "sh", "-c"]
    command.append(
        'psql -v ON_ERROR_STOP=1 -tA -F "|" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"'
    )
    return _compose(*command, sql, timeout=60, check=check)


def _query(sql: str) -> list[list[str]]:
    output = _psql(sql).stdout.strip()
    return [line.split("|") for line in output.splitlines()] if output else []


def _paid_intent(method: str = "pm_test_success") -> str:
    order = {
        "order_reference": f"E2E-{uuid.uuid4().hex[:12]}",
        "amount": CAPTURED,
        "currency": "EUR",
    }
    status, created = _call("POST", "/payments/intents", key=f"e2e-{uuid.uuid4().hex}", body=order)
    assert status == 201
    intent_id = str(created["id"])
    status, _ = _call(
        "POST",
        f"/payments/intents/{intent_id}/confirm",
        key=f"e2e-{uuid.uuid4().hex}",
        body={"payment_method": method},
    )
    assert status == 200
    return intent_id


def _refund(intent_id: str, amount: object, key: str | None = None) -> tuple[int, Any]:
    return _call(
        "POST",
        f"/payments/intents/{intent_id}/refunds",
        key=key or f"e2e-refund-{uuid.uuid4().hex}",
        body={"amount": amount},
    )


def _refunded(intent_id: str) -> int:
    _, intent = _call("GET", f"/payments/intents/{intent_id}")
    return int(intent["refunded_amount"])


def _refund_rows(intent_id: str) -> int:
    uuid.UUID(intent_id)
    return int(_query(f"SELECT count(*) FROM refunds WHERE intent_id = '{intent_id}'")[0][0])


class TestRefundApi:
    def test_a_partial_refund_writes_inverse_ledger_entries_and_the_cumulated_amount(self) -> None:
        intent_id = _paid_intent()

        status, body = _refund(intent_id, 4000)

        assert status == 201
        assert (body["amount"], body["amount_refunded"], body["status"]) == (
            4000,
            4000,
            "succeeded",
        )
        assert _refunded(intent_id) == 4000
        lines = _query(
            "SELECT account, direction, amount FROM ledger_entries WHERE transaction_id IN "
            f"(SELECT transaction_id FROM ledger_entries WHERE intent_id = '{intent_id}' "
            "AND account = 'remboursements') ORDER BY direction"
        )
        assert lines == [["remboursements", "credit", "4000"], ["marchand", "debit", "4000"]]

    def test_4000_then_6001_is_a_conflict_and_6000_refunds_the_rest(self) -> None:
        intent_id = _paid_intent()
        _refund(intent_id, 4000)

        too_much, _ = _refund(intent_id, 6001)
        exact, body = _refund(intent_id, 6000)

        assert too_much == 409
        assert exact == 201
        assert body["amount_refunded"] == CAPTURED
        assert _refunded(intent_id) == CAPTURED
        assert _refund(intent_id, 1)[0] == 409

    def test_the_same_key_returns_the_same_refund_and_a_new_amount_is_a_422(self) -> None:
        intent_id = _paid_intent()
        key = f"e2e-refund-{uuid.uuid4().hex}"
        first_status, first = _refund(intent_id, 4000, key)

        replay_status, replay = _refund(intent_id, 4000, key)
        other_status, _ = _refund(intent_id, 1000, key)

        assert (first_status, replay_status, other_status) == (201, 200, 422)
        assert replay == first
        assert _refund_rows(intent_id) == 1
        assert _refunded(intent_id) == 4000

    @pytest.mark.parametrize("method", ["pm_test_declined", "pm_test_timeout"])
    def test_a_failed_intent_cannot_be_refunded(self, method: str) -> None:
        intent_id = _paid_intent(method)

        assert _refund(intent_id, 100)[0] == 409
        assert _refund_rows(intent_id) == 0

    @pytest.mark.parametrize("amount", [0, -100, 40.5, "4000", True])
    def test_an_invalid_amount_is_a_422(self, amount: object) -> None:
        intent_id = _paid_intent()

        assert _refund(intent_id, amount)[0] == 422
        assert _refund_rows(intent_id) == 0


class TestCeilingUnderAttack:
    def test_parallel_refunds_across_instances_never_exceed_the_captured_amount(self) -> None:
        intent_id = _paid_intent()
        output = _compose(
            *["exec", "-T", "shop", "python", "-c", PARALLEL_SCRIPT],
            f"/payments/intents/{intent_id}/refunds",
            _env_value("PAYMENT_SERVICE_TOKEN_SHOP"),
            "3000",
            "8",
            f"e2e-par-{uuid.uuid4().hex}-",
            timeout=90,
        ).stdout

        statuses = json.loads(output.strip().splitlines()[-1])

        assert statuses == [201, 201, 201, 409, 409, 409, 409, 409]
        assert _refunded(intent_id) == 9000
        assert _query(f"SELECT sum(amount) FROM refunds WHERE intent_id = '{intent_id}'") == [
            ["9000"]
        ]

    def test_the_database_refuses_an_excess_even_without_the_application(self) -> None:
        intent_id = _paid_intent()
        _refund(intent_id, 4000)

        result = _psql(
            "INSERT INTO refunds (id, intent_id, amount, amount_refunded, caller, "
            "idempotency_key, request_hash, created_at) VALUES (gen_random_uuid(), "
            f"'{intent_id}', 6001, 6001, 'shop', 'direct-{uuid.uuid4().hex}', 'h', now())",
            check=False,
        )

        assert result.returncode != 0
        assert "depassent" in result.stderr
        assert _refund_rows(intent_id) == 1
        assert _refunded(intent_id) == 4000


class TestOutboxAndLogs:
    def test_a_refund_queues_a_refund_succeeded_event_in_the_outbox(self) -> None:
        intent_id = _paid_intent()
        _, body = _refund(intent_id, 4000)

        rows = _query(
            f"SELECT event_type, body FROM outbox WHERE intent_id = '{intent_id}' "
            "AND event_type = 'refund.succeeded'"
        )

        assert len(rows) == 1
        event = json.loads(rows[0][1])
        assert event["data"] == {
            "refund_id": body["id"],
            "payment_intent_id": intent_id,
            "order_reference": event["data"]["order_reference"],
            "amount": 4000,
            "amount_refunded": 4000,
            "currency": "EUR",
            "status": "succeeded",
        }

    def test_lines_follow_the_schema_and_never_carry_the_key_or_the_token(self) -> None:
        intent_id = _paid_intent()
        key = f"e2e-refund-{uuid.uuid4().hex}"
        _refund(intent_id, 4000, key)
        _refund(intent_id, 7000, f"e2e-refund-{uuid.uuid4().hex}")  # dépassement refusé

        output = _compose("logs", "--no-color", "payment", timeout=60).stdout
        lines = [line.split("|", 1)[1].strip() for line in output.splitlines() if "| {" in line]
        events = [json.loads(line) for line in lines]
        validator = Draft202012Validator(SCHEMA)

        for event in events:
            assert not list(validator.iter_errors(event)), event
        refund_events = [
            e for e in events if e.get("resource_id") == intent_id or "refund" in e["event"]
        ]
        assert any(e["event"] == "refund.succeeded" for e in refund_events)
        assert any(
            e["event"] == "refund.rejected" and e["reason"] == "amount_exceeds_refundable"
            for e in events
        )
        assert key not in output
        assert _env_value("PAYMENT_SERVICE_TOKEN_SHOP") not in output
