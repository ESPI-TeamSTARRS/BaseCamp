"""Signaux de détection sur la pile (WORK-28) : GET /metrics interne et journal de requêtes.

/metrics se lit depuis le conteneur `shop` (réseau interne `payment-net`), comme le ferait un
collecteur placé sur ce réseau. Il ne doit pas être joignable par la passerelle Traefik.
"""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

from app.caller_identity.__tests__.real_auth import service_token

BASE_URL = os.environ.get("E2E_BASE_URL", "")
REPO_ROOT = Path(__file__).resolve().parents[6]
SCHEMA = json.loads(
    (REPO_ROOT / "docs/development/log-event.schema.json").read_text(encoding="utf-8")
)

SCRAPE_SCRIPT = """
import json, sys, urllib.request, urllib.error
headers = dict(part.split("=", 1) for part in sys.argv[1:])
request = urllib.request.Request("http://payment:8000/metrics", headers=headers)
try:
    response = urllib.request.urlopen(request, timeout=5)
    print(json.dumps({"status": response.status, "type": response.headers["Content-Type"],
                      "body": response.read().decode()}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code, "type": "", "body": error.read().decode()}))
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


def _compose(*args: str, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
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


def _scrape(*headers: str) -> dict[str, Any]:
    output = _compose("exec", "-T", "shop", "python", "-c", SCRAPE_SCRIPT, *headers).stdout
    return json.loads(output.strip().splitlines()[-1])  # type: ignore[no-any-return]


def _call(
    method: str,
    path: str,
    key: str = "",
    body: dict[str, object] | None = None,
    token: str | None = None,
) -> Any:
    output = _compose(
        "exec",
        "-T",
        "shop",
        "python",
        "-c",
        CALL_SCRIPT,
        method,
        path,
        token or service_token(),
        key,
        json.dumps(body) if body else "",
    ).stdout
    result = json.loads(output.strip().splitlines()[-1])
    return result["status"], result["body"]


def _sample(text: str, series: str) -> float:
    match = re.search(rf"^{re.escape(series)} (\S+)$", text, re.MULTILINE)
    assert match, f"série absente : {series}"
    return float(match.group(1))


def _payment_events() -> list[dict[str, Any]]:
    output = _compose("logs", "--no-color", "payment", timeout=120).stdout
    lines = [line.split("|", 1)[1].strip() for line in output.splitlines() if "| {" in line]
    return [json.loads(line) for line in lines]


def _confirm(order: str, key: str) -> str:
    status, created = _call(
        "POST",
        "/payments/intents",
        key=f"create-{key}",
        body={"order_reference": order, "amount": 4990, "currency": "EUR"},
    )
    assert status == 201
    status, _ = _call(
        "POST",
        f"/payments/intents/{created['id']}/confirm",
        key=key,
        body={"payment_method": "pm_test_success"},
    )
    assert status == 200
    return str(created["id"])


class TestMetricsOnTheInternalNetwork:
    def test_shop_reads_the_prometheus_text_format(self) -> None:
        result = _scrape()

        assert result["status"] == 200
        assert result["type"].startswith("text/plain; version=0.0.4")
        assert "# TYPE payment_http_requests_total counter" in result["body"]
        assert _sample(result["body"], "payment_state_up") == 1

    def test_a_confirmation_moves_the_state_gauges_read_from_the_database(self) -> None:
        before = _scrape()["body"]

        _confirm(f"E2E-{uuid.uuid4().hex[:12]}", f"e2e-{uuid.uuid4().hex}")
        after = _scrape()["body"]

        succeeded = 'payment_intents{status="succeeded"}'
        assert _sample(after, succeeded) >= _sample(before, succeeded) + 1
        captured = "payment_captured_amount_cents"
        assert _sample(after, captured) >= _sample(before, captured) + 4990
        assert 'payment_webhook_events{status="dead"}' in after
        assert 'payment_ledger_discrepancies{kind="unbalanced_transaction"} 0' in after

    def test_a_request_through_the_gateway_headers_is_refused(self) -> None:
        result = _scrape("X-Forwarded-For=203.0.113.9")

        assert result["status"] == 404
        assert "payment_" not in result["body"]

    def test_no_secret_identifier_or_raw_path_reaches_a_label(self) -> None:
        order = f"E2E-{uuid.uuid4().hex[:12]}"
        intent_id = _confirm(order, f"e2e-{uuid.uuid4().hex}")

        text = _scrape()["body"]

        for forbidden in (
            service_token(),
            _env_value("PAYMENT_WEBHOOK_SECRET"),
            order,
            intent_id,
        ):
            assert forbidden not in text
        assert set(re.findall(r"([a-z_]+)=\"", text)) <= {"route", "method", "status", "le", "kind"}


@pytest.mark.skipif(not BASE_URL, reason="E2E_BASE_URL non défini")
class TestTheGatewayDoesNotExposeMetrics:
    @pytest.mark.parametrize(
        "path", ["/api/payment/metrics", "/metrics", "/api/shop/payment/metrics"]
    )
    def test_no_route_of_the_gateway_reaches_payment_metrics(self, path: str) -> None:
        response = httpx.get(f"{BASE_URL}{path}", timeout=5.0)

        assert "payment_http_requests_total" not in response.text
        assert "payment_state_up" not in response.text
        assert response.headers.get("content-type", "").split(";")[0] != "text/plain"

    def test_the_payment_prefix_is_a_404_at_the_gateway(self) -> None:
        response = httpx.get(f"{BASE_URL}/api/payment/metrics", timeout=5.0)

        assert response.status_code == 404


class TestRequestLog:
    def test_requests_are_logged_with_route_status_latency_caller_and_request_id(self) -> None:
        order = f"E2E-{uuid.uuid4().hex[:12]}"
        _confirm(order, f"e2e-{uuid.uuid4().hex}")

        events = _payment_events()
        confirmations = [
            e
            for e in events
            if e["event"] == "service.request_completed"
            and e["attributes"]["route"] == "/payments/intents/{intent_id}/confirm"
        ]

        assert confirmations
        line = confirmations[-1]
        assert line["attributes"]["status"] == 200
        assert line["duration_ms"] >= 0
        assert (line["actor_type"], line["actor_id"]) == ("service", "shop")
        assert re.fullmatch(r"[A-Za-z0-9-]{8,64}", line["correlation_id"])
        validator = Draft202012Validator(SCHEMA)
        for event in events:
            assert not list(validator.iter_errors(event)), event

    def test_a_replayed_confirmation_is_a_typed_event(self) -> None:
        key = f"e2e-{uuid.uuid4().hex}"
        intent_id = _confirm(f"E2E-{uuid.uuid4().hex[:12]}", key)
        status, _ = _call(
            "POST",
            f"/payments/intents/{intent_id}/confirm",
            key=key,
            body={"payment_method": "pm_test_success"},
        )

        replays = [
            e
            for e in _payment_events()
            if e["event"] == "payment.confirmation_replayed" and e["resource_id"] == intent_id
        ]

        assert status == 200
        assert len(replays) == 1

    def test_a_rejected_token_is_a_denied_event_and_never_logged(self) -> None:
        bad_token = f"bad-{uuid.uuid4().hex}"
        status, _ = _call("GET", f"/payments/intents/{uuid.uuid4()}", token=bad_token)
        output = _compose("logs", "--no-color", "payment", timeout=120).stdout
        events = _payment_events()

        assert status == 401
        assert bad_token not in output
        assert any(
            e["event"] == "payment.service_authenticated" and e.get("reason") == "invalid_token"
            for e in events
        )
        assert any(
            e["event"] == "service.request_completed" and e.get("reason") == "http_401"
            for e in events
        )
