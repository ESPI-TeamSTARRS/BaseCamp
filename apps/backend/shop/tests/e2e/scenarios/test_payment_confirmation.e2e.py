"""Confirmation de paiement sur la pile réelle : webhook signé de payment, email Mailpit, stock définitif.

Parcours complet par la passerelle : catalogue -> commande -> paiement (intention chez `payment`) ->
confirmation de test -> `payment-worker` livre le webhook signé à `shop` -> commande payée, réservation
de stock définitive, email de confirmation reçu dans Mailpit (`E2E_MAILPIT_URL`), récapitulatif réel.

Le worker doit viser le vrai récepteur de la boutique (`http://shop:8000/webhooks/payment`, la valeur par
défaut de la pile) avec des relances rapprochées (`PAYMENT_WEBHOOK_BACKOFF_BASE_SECONDS=2`). Les scénarios
qui forgent un webhook l'envoient depuis le conteneur `shop` (la route n'est jamais publiée), avec le
secret déjà présent dans son environnement : il ne sort jamais du conteneur ni ne s'affiche.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
MAILPIT_URL = os.environ.get("E2E_MAILPIT_URL", "")
ORDERS_PATH = "/api/shop/orders"
PRODUCT = "boussole-orientation-pro"  # 29,00 EUR, gros stock
QUANTITY = 2
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8

needs_mailbox = pytest.mark.skipif(not MAILPIT_URL, reason="definir E2E_MAILPIT_URL (Mailpit)")
needs_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="docker compose requis (conteneur shop)"
)

# Exécuté DANS le conteneur shop : forge des webhooks signés avec le secret de son environnement.
FORGE_SCRIPT = r"""
import hashlib, hmac, json, os, sys, time, urllib.error, urllib.request

secret = os.environ["APP_PAYMENT_WEBHOOK_SECRET"].encode()
scenario = json.loads(sys.argv[1])
url = "http://127.0.0.1:8000/webhooks/payment"


def post(body, timestamp=None, event_id=None, signature=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    if signature is None:
        digest = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        signature = f"t={timestamp},v1={digest}"
    headers = {"Content-Type": "application/json", "X-Payment-Signature": signature}
    if event_id:
        headers["X-Payment-Event-Id"] = event_id
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def event(event_id, reference):
    return json.dumps({
        "id": event_id, "type": "payment.succeeded", "created_at": "2026-10-21T09:00:00.000Z",
        "data": {"payment_intent_id": "pi-forge", "order_reference": reference,
                 "amount": 100, "currency": "EUR", "status": "succeeded"},
    }, separators=(",", ":")).encode()


body = event(scenario["event_id"], scenario["reference"])
now = int(time.time())
results = {
    "first": post(body, event_id=scenario["event_id"]),
    "replay": post(body, event_id=scenario["event_id"]),
    "stale": post(body, timestamp=int(time.time()) - 400, event_id=scenario["event_id"]),
    "altered": post(
        body.replace(b'"amount":100', b'"amount":1'),
        event_id=scenario["event_id"],
        signature=f"t={now},v1={hmac.new(secret, f'{now}.'.encode() + body, hashlib.sha256).hexdigest()}",
    ),
    "unsigned": post(body, event_id=scenario["event_id"], signature="t=1,v1=00"),
}
print(json.dumps(results))
"""

REPLAY_SCRIPT = r"""
import hashlib, hmac, json, os, sys, time, urllib.request

secret = os.environ["APP_PAYMENT_WEBHOOK_SECRET"].encode()
event_id, reference = sys.argv[1], sys.argv[2]
body = json.dumps({
    "id": event_id, "type": "payment.succeeded", "created_at": "2026-10-21T09:00:00.000Z",
    "data": {"payment_intent_id": "pi-forge", "order_reference": reference,
             "amount": 100, "currency": "EUR", "status": "succeeded"},
}, separators=(",", ":")).encode()
t = int(time.time())
sig = hmac.new(secret, f"{t}.".encode() + body, hashlib.sha256).hexdigest()
request = urllib.request.Request(
    "http://127.0.0.1:8000/webhooks/payment", data=body, method="POST",
    headers={"Content-Type": "application/json", "X-Payment-Signature": f"t={t},v1={sig}",
             "X-Payment-Event-Id": event_id},
)
print(urllib.request.urlopen(request, timeout=5).read().decode())
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


def _new_email() -> str:
    return f"e2e.confirmation.{uuid.uuid4().hex[:12]}@example.org"


def _place_order(client: httpx.Client, email: str) -> dict[str, Any]:
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
    response = _post(client, ORDERS_PATH, body, {"Idempotency-Key": f"e2e-{uuid.uuid4().hex}"})
    assert response.status_code == 201
    return dict(response.json())


def _wait_for(check: Callable[[], Any], seconds: float, message: str) -> Any:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(1.0)
    pytest.fail(message)


def _mails(address: str) -> list[dict[str, Any]]:
    with httpx.Client(base_url=MAILPIT_URL, timeout=5.0) as mailbox:
        found = mailbox.get("/api/v1/search", params={"query": f"to:{address}"}).json()
        return [
            mailbox.get(f"/api/v1/message/{item['ID']}").json()
            for item in found.get("messages", [])
        ]


def _compose(*args: str, timeout: int = 60) -> str:
    result = subprocess.run(  # noqa: S603 - commande fixe, arguments des tests uniquement
        ["docker", "compose", *args],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-300:]
    return result.stdout


def _psql(sql: str) -> str:
    return _compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "shop", "-At", "-c", sql
    )


def _status(client: httpx.Client, number: str, email: str) -> str:
    response = client.post(f"{ORDERS_PATH}/lookup", json={"orderNumber": number, "email": email})
    return str(response.json().get("status")) if response.status_code == 200 else ""


@needs_mailbox
class TestFullJourney:
    def test_paying_an_order_confirms_it_by_webhook_and_sends_the_email(
        self, client: httpx.Client
    ) -> None:
        email = _new_email()
        order = _place_order(client, email)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"

        intent = _post(client, pay, None)
        paid = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_success"})

        assert intent.status_code == 201
        assert paid.status_code == 200 and paid.json()["order_status"] == "paid"
        mails = _wait_for(lambda: _mails(email), 40, "l'email de confirmation n'est pas reçu")
        assert len(mails) == 1
        mail = mails[0]
        total = f"{order['total_cents'] // 100},{order['total_cents'] % 100:02d} EUR"
        assert order["number"] in mail["Subject"]
        assert order["number"] in mail["Text"] and total in mail["Text"]
        assert [r["Address"] for r in mail["To"]] == [email]

    @needs_docker
    def test_the_webhook_makes_the_stock_reservation_definitive(self, client: httpx.Client) -> None:
        email = _new_email()
        order = _place_order(client, email)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"
        _post(client, pay, None)
        _post(client, f"{pay}/confirm", {"payment_method": "pm_test_success"})

        def committed() -> bool:
            order_id = str(uuid.UUID(order["id"]))  # UUID validé : aucune injection possible
            states = _psql(
                f"select status from stock_reservations where order_id = '{order_id}'"  # noqa: S608
            ).split()
            return states == ["committed"]

        _wait_for(committed, 40, "la réservation de stock n'est pas devenue définitive")
        assert _status(client, order["number"], email) == "paid"
        order_id = str(uuid.UUID(order["id"]))  # UUID validé : aucune injection possible
        events = _psql(
            f"select count(*) from payment_webhook_events where paid_order_id = '{order_id}'"  # noqa: S608
        )
        assert events.strip() == "1"

    def test_the_success_page_serves_and_the_order_recap_is_the_servers(
        self, client: httpx.Client
    ) -> None:
        email = _new_email()
        order = _place_order(client, email)

        page = client.get("/success", params={"commande": order["number"]})
        lookup = client.post(
            f"{ORDERS_PATH}/lookup", json={"orderNumber": order["number"], "email": email}
        )

        assert page.status_code == 200 and order["number"] in page.text
        recap = lookup.json()
        assert recap["total_cents"] == order["total_cents"]
        assert [(line["quantity"]) for line in recap["lines"]] == [QUANTITY]

    def test_a_declined_payment_sends_no_email_and_leaves_the_order_payable(
        self, client: httpx.Client
    ) -> None:
        email = _new_email()
        order = _place_order(client, email)
        pay = f"{ORDERS_PATH}/{order['id']}/pay"
        _post(client, pay, None)

        declined = _post(client, f"{pay}/confirm", {"payment_method": "pm_test_declined"})
        time.sleep(8)  # laisse au worker le temps de livrer payment.failed

        assert declined.status_code == 200 and declined.json()["order_status"] == "pending_payment"
        assert _mails(email) == []
        assert _status(client, order["number"], email) == "pending_payment"


@needs_docker
class TestSignedWebhookOnTheStack:
    def _forge(self, reference: str) -> dict[str, list[Any]]:
        scenario = json.dumps({"event_id": str(uuid.uuid4()), "reference": reference})
        output = _compose("exec", "-T", "shop", "python", "-c", FORGE_SCRIPT, scenario)
        return dict(json.loads(output))

    def test_rejections_are_401_and_a_replay_is_acknowledged_without_effect(self) -> None:
        results = self._forge("BC-INCONNU0001")

        assert results["first"] == [200, {"status": "ignored"}]
        assert results["replay"] == [200, {"status": "replayed"}]
        for name in ("stale", "altered", "unsigned"):
            assert results[name] == [401, {"detail": "Signature invalide."}], name

    def test_a_replay_is_still_recognised_after_the_shop_restarts(self) -> None:
        event_id = str(uuid.uuid4())
        first = _compose(
            "exec", "-T", "shop", "python", "-c", REPLAY_SCRIPT, event_id, "BC-INCONNU0002"
        )
        _compose("restart", "shop", timeout=120)
        _wait_for(
            lambda: "healthy" in _compose("ps", "shop", "--format", "{{.Status}}"),
            60,
            "shop ne redevient pas sain",
        )

        again = _compose(
            "exec", "-T", "shop", "python", "-c", REPLAY_SCRIPT, event_id, "BC-INCONNU0002"
        )

        assert json.loads(first) == {"status": "ignored"}
        assert json.loads(again) == {"status": "replayed"}


class TestGatewayDoesNotExposeTheWebhook:
    def test_the_webhook_route_is_never_reachable_from_outside(self, client: httpx.Client) -> None:
        for path in ("/api/shop/webhooks/payment", "/api/shop/webhooks/"):
            response = client.post(path, content=b"{}", headers={"X-Payment-Signature": "t=1,v1=0"})

            # Le front (route par défaut de la passerelle) répond 404/405 ou redirige le slash final :
            # jamais la réponse du webhook du shop (200 accusé, 400 ou 401).
            assert response.status_code in (404, 405, 308), path
            assert "Signature invalide" not in response.text
