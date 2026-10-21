"""Remboursement sur la pile réelle (WORK-29) : payment rembourse, `refund.succeeded` met la commande à jour.

Parcours par la passerelle : commande -> paiement chez `payment` -> webhook `payment.succeeded` ->
remboursement partiel puis du reste (appelé depuis le conteneur `shop`, jamais joignable depuis l'hôte) ->
webhook `refund.succeeded` -> commande « remboursée ». Les altérations (rejeu, cumul au-delà du total,
signature fausse, double remboursement) sont forgées dans le conteneur `shop` avec le secret de son
environnement : il ne sort jamais du conteneur ni ne s'affiche. Le worker doit viser le vrai récepteur de
la boutique (`http://shop:8000/webhooks/payment`) avec des relances rapprochées
(`PAYMENT_WEBHOOK_BACKOFF_BASE_SECONDS=2`). Le contrôle du grand livre (`ledger-check`) clôt le scénario :
il doit rester cohérent.
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
REPO_ROOT = Path(__file__).resolve().parents[6]  # COMPOSE_FILE est relatif à la racine du dépôt
ORDERS_PATH = "/api/shop/orders"
PRODUCT = "boussole-orientation-pro"  # 29,00 EUR, gros stock
QUANTITY = 2
PARTIAL_CENTS = 1000
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8
DELIVERY_SECONDS = 40
SETTLE_SECONDS = 5  # laisse au worker le temps de livrer un événement qui n'aurait pas dû exister
LEDGER_CHECK = ["python", "-m", "app.ledgercheck.presentation.cli"]

pytestmark = pytest.mark.skipif(
    not shutil.which("docker"), reason="docker compose requis (conteneur shop)"
)

# Exécuté DANS le conteneur shop : appelle payment avec le jeton de service de la boutique.
REFUND_SCRIPT = r"""
import json, os, sys, urllib.error, urllib.request

intent_id, amount, key = sys.argv[1:4]
request = urllib.request.Request(
    f"http://payment:8000/payments/intents/{intent_id}/refunds",
    data=json.dumps({"amount": int(amount)}).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + os.environ["APP_PAYMENT_SERVICE_TOKEN"],
        "Idempotency-Key": key,
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        print(json.dumps({"status": response.status}))
except urllib.error.HTTPError as error:
    print(json.dumps({"status": error.code}))
"""

# Exécuté DANS le conteneur shop : forge un refund.succeeded signé avec le secret de son environnement.
FORGE_SCRIPT = r"""
import hashlib, hmac, json, os, sys, time, urllib.error, urllib.request

secret = os.environ["APP_PAYMENT_WEBHOOK_SECRET"].encode()
event_id, reference, cumulative = sys.argv[1], sys.argv[2], int(sys.argv[3])
body = json.dumps({
    "id": event_id, "type": "refund.succeeded", "created_at": "2026-10-21T09:00:00.000Z",
    "data": {"refund_id": "r-forge", "payment_intent_id": "pi-forge", "order_reference": reference,
             "amount": cumulative, "amount_refunded": cumulative, "currency": "EUR",
             "status": "succeeded"},
}, separators=(",", ":")).encode()


def post(payload, signature=None):
    t = int(time.time())
    if signature is None:
        digest = hmac.new(secret, f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
        signature = f"t={t},v1={digest}"
    request = urllib.request.Request(
        "http://127.0.0.1:8000/webhooks/payment", data=payload, method="POST",
        headers={"Content-Type": "application/json", "X-Payment-Signature": signature,
                 "X-Payment-Event-Id": event_id},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


altered = body.replace(f'"amount_refunded":{cumulative}'.encode(), b'"amount_refunded":1')
print(json.dumps({
    "first": post(body), "replay": post(body), "altered": post(altered, signature="t=1,v1=00"),
}))
"""


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=15.0)


def _post(client: httpx.Client, path: str, body: Any, headers: dict[str, str] | None = None) -> Any:
    """POST ; sur 429 de la passerelle on patiente puis on rejoue (les routes sont idempotentes)."""
    response = client.post(path, json=body, headers=headers)
    for _ in range(RATE_LIMIT_ATTEMPTS):
        if response.status_code != 429:
            break
        time.sleep(RATE_LIMIT_PAUSE_SECONDS)
        response = client.post(path, json=body, headers=headers)
    return response


def _run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - commande fixe, arguments des tests uniquement
        ["docker", "compose", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=REPO_ROOT,
    )


def _compose(*args: str) -> str:
    result = _run(*args)
    assert result.returncode == 0, result.stderr[-300:]
    return result.stdout


def _psql(sql: str) -> str:
    return _compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "shop", "-At", "-c", sql
    ).strip()


def _in_shop(script: str, *args: str) -> dict[str, Any]:
    output = _compose("exec", "-T", "shop", "python", "-c", script, *args)
    return dict(json.loads(output.strip().splitlines()[-1]))


def _wait_for(check: Callable[[], Any], message: str) -> Any:
    deadline = time.monotonic() + DELIVERY_SECONDS
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(1.0)
    pytest.fail(message)


class _PaidOrder:
    """Une commande payée par la passerelle, dont le webhook `payment.succeeded` est arrivé."""

    def __init__(self, client: httpx.Client) -> None:
        self.email = f"e2e.remboursement.{uuid.uuid4().hex[:12]}@example.org"
        body = {
            "email": self.email,
            "shippingAddress": {
                "fullName": "Client E2E",
                "line1": "1 rue du Test",
                "postalCode": "75001",
                "city": "Paris",
                "country": "FR",
            },
            "lines": [{"productId": PRODUCT, "quantity": QUANTITY}],
        }
        order = _post(client, ORDERS_PATH, body, {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})
        assert order.status_code == 201
        placed = order.json()
        self.id = str(uuid.UUID(placed["id"]))  # UUID validé : aucune injection possible
        self.number = str(placed["number"])
        self.total = int(placed["total_cents"])
        pay = f"{ORDERS_PATH}/{self.id}/pay"
        intent = _post(client, pay, None)
        assert intent.status_code == 201
        self.intent_id = str(uuid.UUID(intent.json()["payment_intent_id"]))
        paid = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_success"})
        assert paid.status_code == 200 and paid.json()["order_status"] == "paid"
        _wait_for(self._payment_webhook_received, "le webhook payment.succeeded n'est pas arrivé")

    def _payment_webhook_received(self) -> bool:
        count = _psql(
            f"select count(*) from payment_webhook_events where paid_order_id = '{self.id}'"  # noqa: S608
        )
        return count == "1"

    def refund(self, amount: int, key: str | None = None) -> int:
        result = _in_shop(
            REFUND_SCRIPT, self.intent_id, str(amount), key or f"e2e-{uuid.uuid4().hex}"
        )
        return int(result["status"])

    def status(self) -> str:
        return _psql(f"select status from orders where id = '{self.id}'")  # noqa: S608

    def refunded(self) -> int:
        value = _psql(f"select refunded_cents from order_refunds where order_id = '{self.id}'")  # noqa: S608
        return int(value) if value else 0

    def lookup_status(self, client: httpx.Client) -> str:
        response = _post(
            client, f"{ORDERS_PATH}/lookup", {"orderNumber": self.number, "email": self.email}
        )
        return str(response.json().get("status"))


class TestRefundJourney:
    def test_a_partial_then_a_full_refund_update_the_order(self, client: httpx.Client) -> None:
        order = _PaidOrder(client)

        assert order.refund(PARTIAL_CENTS) == 201
        _wait_for(
            lambda: order.refunded() == PARTIAL_CENTS, "le remboursement partiel n'arrive pas"
        )
        assert order.status() == "paid"

        assert order.refund(order.total - PARTIAL_CENTS) == 201
        _wait_for(lambda: order.status() == "refunded", "la commande n'est pas remboursée")
        assert order.refunded() == order.total
        assert order.lookup_status(client) == "refunded"

    def test_a_double_refund_beyond_the_captured_amount_changes_nothing(
        self, client: httpx.Client
    ) -> None:
        order = _PaidOrder(client)
        assert order.refund(order.total) == 201
        _wait_for(lambda: order.status() == "refunded", "la commande n'est pas remboursée")

        second = order.refund(order.total)
        time.sleep(SETTLE_SECONDS)

        assert second == 409
        assert (order.status(), order.refunded()) == ("refunded", order.total)

    def test_the_same_refund_replayed_with_its_key_is_not_applied_twice(
        self, client: httpx.Client
    ) -> None:
        order = _PaidOrder(client)
        key = f"e2e-{uuid.uuid4().hex}"

        first = order.refund(PARTIAL_CENTS, key)
        replay = order.refund(PARTIAL_CENTS, key)
        _wait_for(lambda: order.refunded() == PARTIAL_CENTS, "le remboursement n'arrive pas")
        time.sleep(SETTLE_SECONDS)

        assert (first, replay) == (201, 200)
        assert order.refunded() == PARTIAL_CENTS


class TestForgedRefundEvents:
    def test_a_replayed_event_is_acknowledged_once_and_a_bad_signature_is_refused(
        self, client: httpx.Client
    ) -> None:
        order = _PaidOrder(client)

        results = _in_shop(FORGE_SCRIPT, str(uuid.uuid4()), order.number, "500")

        assert results["first"] == [200, {"status": "applied"}]
        assert results["replay"] == [200, {"status": "replayed"}]
        assert results["altered"][0] == 401
        assert order.refunded() == 500

    def test_a_cumulative_above_the_order_total_never_marks_it_refunded(
        self, client: httpx.Client
    ) -> None:
        order = _PaidOrder(client)

        results = _in_shop(FORGE_SCRIPT, str(uuid.uuid4()), order.number, str(order.total + 1))

        assert results["first"] == [200, {"status": "ignored"}]
        assert (order.status(), order.refunded()) == ("paid", 0)


class TestLedgerStaysConsistent:
    def test_the_ledger_check_is_green_after_the_scenario(self) -> None:
        result = _run("exec", "-T", "payment", *LEDGER_CHECK)

        assert result.returncode == 0, result.stdout[-300:]
