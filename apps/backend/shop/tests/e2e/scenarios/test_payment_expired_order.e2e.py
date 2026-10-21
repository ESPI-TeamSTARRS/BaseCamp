"""Paiement après expiration de la commande (WORK-30) : la boutique refuse (409), payment rembourse seul.

Parcours sur la pile réelle : commande -> intention chez `payment` -> la commande expire (délai dépassé,
traitement d'expiration lancé dans le conteneur `shop`) -> le paiement aboutit chez `payment` (confirmé
depuis le conteneur `shop`, comme le ferait un client lent) -> `payment-worker` livre `payment.succeeded`,
la boutique répond 409 « commande expirée » -> l'événement passe `rejected_by_receiver` et un remboursement
total automatique est écrit (une seule fois, même si le scénario est rejoué) -> le grand livre reste
cohérent (`ledger-check`). Le worker doit viser le vrai récepteur de la boutique
(`http://shop:8000/webhooks/payment`) avec des relances rapprochées
(`PAYMENT_WEBHOOK_BACKOFF_BASE_SECONDS=2`).
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
RATE_LIMIT_PAUSE_SECONDS = 6.5  # la passerelle limite /orders a 10/min (un jeton toutes les 6 s)
RATE_LIMIT_ATTEMPTS = 8
DELIVERY_SECONDS = 40
SETTLE_SECONDS = 6  # laisse au worker le temps de livrer un événement qui n'aurait pas dû exister
LEDGER_CHECK = ["python", "-m", "app.ledgercheck.presentation.cli"]

pytestmark = pytest.mark.skipif(
    not shutil.which("docker"), reason="docker compose requis (conteneur shop)"
)

# Exécuté DANS le conteneur shop : appelle payment avec le jeton de service de la boutique.
CONFIRM_SCRIPT = r"""
import json, os, sys, urllib.error, urllib.request

intent_id, key = sys.argv[1:3]
request = urllib.request.Request(
    f"http://payment:8000/payments/intents/{intent_id}/confirm",
    data=json.dumps({"payment_method": "pm_test_success"}).encode(),
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


def _shop_psql(sql: str) -> str:
    return _compose(
        "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "shop", "-At", "-c", sql
    ).strip()


def _payment_psql(sql: str) -> str:
    return _compose(
        "exec",
        "-T",
        "payment-db",
        "sh",
        "-c",
        'psql -v ON_ERROR_STOP=1 -tA -F "|" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"',
        sql,
    ).strip()


def _wait_for(check: Callable[[], Any], message: str) -> Any:
    deadline = time.monotonic() + DELIVERY_SECONDS
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(1.0)
    pytest.fail(message)


class _LateOrder:
    """Une commande expirée dont l'intention de paiement existe chez payment mais n'est pas confirmée."""

    def __init__(self, client: httpx.Client) -> None:
        body = {
            "email": f"e2e.tardif.{uuid.uuid4().hex[:12]}@example.org",
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
        self.total = int(placed["total_cents"])
        intent = _post(client, f"{ORDERS_PATH}/{self.id}/pay", None)
        assert intent.status_code == 201
        self.intent_id = str(uuid.UUID(intent.json()["payment_intent_id"]))
        self._expire()

    def _expire(self) -> None:
        _shop_psql(
            f"update orders set created_at = now() - interval '2 hours' where id = '{self.id}'"  # noqa: S608
        )
        _compose("exec", "-T", "shop", "python", "-m", "app.order_expiration", "--once")
        assert self.status() == "expired"

    def status(self) -> str:
        return _shop_psql(f"select status from orders where id = '{self.id}'")  # noqa: S608

    def pay_at_payment(self) -> int:
        """Le client lent paie quand même : confirmation directe chez payment (shop refuserait en 409)."""
        output = _compose(
            "exec",
            "-T",
            "shop",
            "python",
            "-c",
            CONFIRM_SCRIPT,
            self.intent_id,
            f"e2e-{uuid.uuid4().hex}",
        )
        return int(json.loads(output.strip().splitlines()[-1])["status"])

    def outbox_status(self) -> str:
        return _payment_psql(
            f"select status from outbox where intent_id = '{self.intent_id}' "  # noqa: S608
            "and event_type = 'payment.succeeded'"
        )

    def refunded(self) -> int:
        value = _payment_psql(
            f"select refunded_amount from payment_intents where id = '{self.intent_id}'"  # noqa: S608
        )
        return int(value) if value else 0

    def refund_rows(self) -> int:
        return int(
            _payment_psql(f"select count(*) from refunds where intent_id = '{self.intent_id}'")  # noqa: S608
        )


class TestPaymentAfterExpiration:
    def test_the_shop_rejects_and_payment_refunds_the_whole_amount_once(
        self, client: httpx.Client
    ) -> None:
        order = _LateOrder(client)

        assert order.pay_at_payment() == 200
        _wait_for(
            lambda: order.outbox_status() == "rejected_by_receiver",
            "l'événement n'est pas passé rejected_by_receiver",
        )

        assert order.refunded() == order.total
        assert order.refund_rows() == 1
        assert order.status() == "expired"  # la commande n'est jamais ressuscitée
        time.sleep(SETTLE_SECONDS)  # aucun second remboursement, aucune relance de l'événement clos
        assert (order.refunded(), order.refund_rows()) == (order.total, 1)
        assert order.outbox_status() == "rejected_by_receiver"

    def test_the_stock_of_the_expired_order_stays_released(self, client: httpx.Client) -> None:
        order = _LateOrder(client)

        order.pay_at_payment()
        _wait_for(lambda: order.outbox_status() == "rejected_by_receiver", "événement non clos")

        reservations = _shop_psql(
            f"select status from stock_reservations where order_id = '{order.id}'"  # noqa: S608
        ).split()
        assert reservations == ["released"]


class TestLedgerStaysConsistent:
    def test_the_ledger_check_is_green_after_the_automatic_refunds(self) -> None:
        result = _run("exec", "-T", "payment", *LEDGER_CHECK)

        assert result.returncode == 0, result.stdout[-300:]
