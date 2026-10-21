"""Webhook signé payment -> shop sur la pile (WORK-23), contre un récepteur factice.

La boutique n'expose pas encore sa route de réception (WORK-13) : un récepteur factice est lancé
dans le conteneur `shop` (port 9100) et le worker `payment-worker` est pointé dessus par
`PAYMENT_WEBHOOK_URL=http://shop:9100/webhooks/payment` (voir le job `stack-e2e`). Les appels à
payment partent du conteneur shop, comme le fait le vrai appelant. Tous les scénarios s'exécutent
avec les valeurs de pile `PAYMENT_WEBHOOK_BACKOFF_BASE_SECONDS=2` (relances rapprochées).
"""

import hashlib
import hmac
import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.caller_identity.__tests__.real_auth import operator_token, service_token

REPO_ROOT = Path(__file__).resolve().parents[6]
RECEIVER_PORT = 9100
TOLERANCE_SECONDS = 300
SCHEMA = json.loads(
    (REPO_ROOT / "docs/development/log-event.schema.json").read_text(encoding="utf-8")
)

RECEIVER_SCRIPT = r"""
import json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
received = []

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        received.append({
            "signature": self.headers.get("X-Payment-Signature"),
            "event_id": self.headers.get("X-Payment-Event-Id"),
            "body": body,
            "received_at": time.time(),
        })
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        data = json.dumps(received).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Handler).serve_forever()
"""

READ_RECEIVER_SCRIPT = f"""
import sys, urllib.request
sys.stdout.write(urllib.request.urlopen("http://127.0.0.1:{RECEIVER_PORT}/", timeout=3).read().decode())
"""

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
) -> tuple[int, dict[str, Any]]:
    token = operator_token() if path.endswith("/refunds") else service_token()
    output = _compose(
        *["exec", "-T", "shop", "python", "-c", CALL_SCRIPT],
        method,
        path,
        token,
        key,
        json.dumps(body) if body else "",
        timeout=60,
    ).stdout
    result = json.loads(output.strip().splitlines()[-1])
    return result["status"], result["body"]


def _confirmed_payment(method: str = "pm_test_success") -> str:
    """Crée puis confirme une intention; renvoie son identifiant."""
    order = {"order_reference": f"E2E-{uuid.uuid4().hex[:12]}", "amount": 4990, "currency": "EUR"}
    status, created = _call("POST", "/payments/intents", key=f"e2e-{uuid.uuid4().hex}", body=order)
    assert status == 201
    intent_id = str(created["id"])
    status, _ = _call(
        "POST",
        f"/payments/intents/{intent_id}/confirm",
        key=f"e2e-{uuid.uuid4().hex}",
        body={"payment_method": method},
    )
    assert status == 200, "une panne du shop ne doit jamais empêcher de confirmer"
    return intent_id


def _psql(sql: str) -> str:
    command = ["exec", "-T", "payment-db", "sh", "-c"]
    command.append(
        'psql -v ON_ERROR_STOP=1 -tA -F "|" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"'
    )
    return _compose(*command, sql, timeout=60).stdout.strip()


def _outbox_row(intent_id: str) -> list[str]:
    uuid.UUID(intent_id)
    row = _psql(
        f"SELECT id, event_type, status, attempts FROM outbox WHERE intent_id = '{intent_id}'"
    )
    return row.split("|") if row else []


def _read_receiver() -> list[dict[str, Any]] | None:
    result = _compose(
        *["exec", "-T", "shop", "python", "-c", READ_RECEIVER_SCRIPT], timeout=30, check=False
    )
    return json.loads(result.stdout) if result.returncode == 0 else None


def _start_receiver() -> None:
    if _read_receiver() is not None:
        return
    _compose("exec", "-d", "-T", "shop", "python", "-c", RECEIVER_SCRIPT, str(RECEIVER_PORT))
    _wait_for(lambda: _read_receiver() is not None, 20, "le récepteur factice ne démarre pas")


def _restart_shop() -> None:
    """Arrête puis relance le conteneur shop (le récepteur factice y disparaît)."""
    _compose("restart", "shop", timeout=120)
    _compose("up", "-d", "--wait", "--wait-timeout", "90", "shop", timeout=120)


def _wait_for(condition: Callable[[], object], seconds: float, message: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(1)
    pytest.fail(message)


def _deliveries(intent_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in _read_receiver() or []
        if json.loads(item["body"])["data"]["payment_intent_id"] == intent_id
    ]


def _signature_is_valid(delivery: dict[str, Any]) -> bool:
    """Recalcule la signature publiée (t=...,v1=...) sans réutiliser le code du service."""
    parts = dict(part.split("=", 1) for part in delivery["signature"].split(","))
    expected = hmac.new(
        _env_value("PAYMENT_WEBHOOK_SECRET").encode(),
        f"{parts['t']}.{delivery['body']}".encode(),
        hashlib.sha256,
    ).hexdigest()
    fresh = abs(time.time() - int(parts["t"])) <= TOLERANCE_SECONDS
    return fresh and hmac.compare_digest(expected, parts["v1"])


@pytest.fixture
def receiver() -> Iterator[None]:
    _compose("up", "-d", "--wait", "payment-worker", timeout=120)
    _start_receiver()
    yield
    _compose("up", "-d", "payment-worker", timeout=120)


class TestSignedDelivery:
    def test_a_confirmed_payment_is_delivered_once_with_a_valid_signature(
        self, receiver: None
    ) -> None:
        intent_id = _confirmed_payment()

        _wait_for(lambda: _deliveries(intent_id), 30, "le webhook n'est pas livré")

        (delivery,) = _deliveries(intent_id)
        body = json.loads(delivery["body"])
        assert body["type"] == "payment.succeeded"
        assert body["data"] == {
            "payment_intent_id": intent_id,
            "order_reference": body["data"]["order_reference"],
            "amount": 4990,
            "currency": "EUR",
            "status": "succeeded",
        }
        assert delivery["event_id"] == body["id"]
        assert _signature_is_valid(delivery)
        _wait_for(lambda: _outbox_row(intent_id)[2:3] == ["delivered"], 15, "outbox non livrée")
        assert _outbox_row(intent_id)[1:] == ["payment.succeeded", "delivered", "1"]

    def test_a_declined_payment_emits_payment_failed(self, receiver: None) -> None:
        intent_id = _confirmed_payment("pm_test_declined")

        _wait_for(lambda: _deliveries(intent_id), 30, "le webhook n'est pas livré")

        (delivery,) = _deliveries(intent_id)
        assert json.loads(delivery["body"])["type"] == "payment.failed"
        assert _signature_is_valid(delivery)

    def test_a_refund_emits_a_signed_refund_succeeded_event(self, receiver: None) -> None:
        intent_id = _confirmed_payment()
        status, refund = _call(
            "POST",
            f"/payments/intents/{intent_id}/refunds",
            key=f"e2e-{uuid.uuid4().hex}",
            body={"amount": 4000},
        )
        assert status == 201

        _wait_for(lambda: len(_deliveries(intent_id)) == 2, 30, "le webhook n'est pas livré")

        by_type = {json.loads(item["body"])["type"]: item for item in _deliveries(intent_id)}
        delivery = by_type["refund.succeeded"]
        body = json.loads(delivery["body"])
        assert body["data"] == {
            "refund_id": refund["id"],
            "payment_intent_id": intent_id,
            "order_reference": body["data"]["order_reference"],
            "amount": 4000,
            "amount_refunded": 4000,
            "currency": "EUR",
            "status": "succeeded",
        }
        assert delivery["event_id"] == body["id"]
        assert _signature_is_valid(delivery)

    def test_a_replayed_confirmation_does_not_emit_a_second_event(self, receiver: None) -> None:
        order = {
            "order_reference": f"E2E-{uuid.uuid4().hex[:12]}",
            "amount": 4990,
            "currency": "EUR",
        }
        _, created = _call("POST", "/payments/intents", key=f"e2e-{uuid.uuid4().hex}", body=order)
        path, key = f"/payments/intents/{created['id']}/confirm", f"e2e-{uuid.uuid4().hex}"
        body = {"payment_method": "pm_test_success"}

        _call("POST", path, key=key, body=body)
        _call("POST", path, key=key, body=body)

        _wait_for(lambda: _deliveries(created["id"]), 30, "le webhook n'est pas livré")
        time.sleep(5)
        assert len(_deliveries(created["id"])) == 1
        assert _psql(f"SELECT count(*) FROM outbox WHERE intent_id = '{created['id']}'") == "1"

    def test_the_secret_and_signatures_never_reach_the_logs_and_lines_follow_the_schema(
        self, receiver: None
    ) -> None:
        intent_id = _confirmed_payment()
        _wait_for(lambda: _deliveries(intent_id), 30, "le webhook n'est pas livré")

        output = _compose("logs", "--no-color", "payment-worker", "payment").stdout
        lines = [line.split("|", 1)[1].strip() for line in output.splitlines() if "| {" in line]
        events = [json.loads(line) for line in lines]
        validator = Draft202012Validator(SCHEMA)

        for event in events:
            assert not list(validator.iter_errors(event)), event
        assert any(event["event"] == "webhook.delivered" for event in events)
        assert any(event["event"] == "webhook.event_queued" for event in events)
        assert _env_value("PAYMENT_WEBHOOK_SECRET") not in output
        assert "v1=" not in output


class TestReliability:
    def test_delivery_resumes_by_itself_after_the_shop_stops_and_restarts(self) -> None:
        _compose("up", "-d", "--wait", "payment-worker", timeout=120)
        _restart_shop()  # le récepteur factice n'existe plus : le port est fermé
        intent_id = _confirmed_payment()  # la confirmation passe malgré le shop injoignable
        _wait_for(lambda: _outbox_row(intent_id)[3:4] not in ([], ["0"]), 20, "pas de tentative")
        event_id = _outbox_row(intent_id)[0]

        _restart_shop()
        _start_receiver()
        _wait_for(lambda: _deliveries(intent_id), 120, "la livraison n'a pas repris")

        (delivery,) = _deliveries(intent_id)
        assert delivery["event_id"] == event_id, "l'identifiant ne change jamais entre tentatives"
        assert _signature_is_valid(delivery)
        _wait_for(lambda: _outbox_row(intent_id)[2:3] == ["delivered"], 15, "outbox non livrée")
        assert int(_outbox_row(intent_id)[3]) >= 2

    def test_a_dead_event_is_requeued_by_the_ops_command_with_the_same_id(self) -> None:
        _compose("up", "-d", "--wait", "payment-worker", timeout=120)
        _start_receiver()
        _compose("stop", "payment-worker", timeout=60)  # on maîtrise le moment de la livraison
        try:
            intent_id = _confirmed_payment()
            event_id = _outbox_row(intent_id)[0]
            _psql(
                "UPDATE outbox SET status = 'dead', attempts = 6, last_error = 'http_500' "
                f"WHERE intent_id = '{intent_id}'"
            )
            requeue = [
                *["run", "--rm", "--no-deps", "-T", "payment-worker"],
                *["python", "-m", "app.webhook.presentation.requeue_main"],
            ]
            nothing = _compose(*requeue, "--event-id", str(uuid.uuid4()), check=False)
            done = _compose(*requeue, "--event-id", event_id)
        finally:
            _compose("start", "payment-worker", timeout=60)

        assert nothing.returncode == 1
        assert done.returncode == 0
        _wait_for(lambda: _deliveries(intent_id), 30, "l'événement relancé n'est pas livré")
        # Une seconde relance du même événement : même identifiant, même corps (la boutique déduplique).
        _wait_for(lambda: _outbox_row(intent_id)[2:3] == ["delivered"], 15, "outbox non livrée")
        _psql(f"UPDATE outbox SET status = 'dead' WHERE intent_id = '{intent_id}'")
        _compose(*requeue, "--event-id", event_id)
        _wait_for(lambda: len(_deliveries(intent_id)) == 2, 30, "la relance n'est pas livrée")
        first, second = _deliveries(intent_id)
        assert (first["event_id"], first["body"]) == (second["event_id"], second["body"])
        assert event_id == first["event_id"]
