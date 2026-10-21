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
import time
import uuid

import httpx
import pytest

from app.__tests__.payment_stack import (
    LEDGER_CHECK,
    ORDERS_PATH,
    compose,
    needs_docker,
    new_client,
    place_order,
    post,
    run,
    shop_psql,
    wait_for,
)

SETTLE_SECONDS = 6  # laisse au worker le temps de livrer un événement qui n'aurait pas dû exister

pytestmark = needs_docker

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
    return new_client()


def _payment_psql(sql: str) -> str:
    return compose(
        "exec",
        "-T",
        "payment-db",
        "sh",
        "-c",
        'psql -v ON_ERROR_STOP=1 -tA -F "|" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$0"',
        sql,
    ).strip()


class _LateOrder:
    """Une commande expirée dont l'intention de paiement existe chez payment mais n'est pas confirmée."""

    def __init__(self, client: httpx.Client) -> None:
        placed, _ = place_order(client, "e2e.tardif")
        self.id = str(uuid.UUID(placed["id"]))  # UUID validé : aucune injection possible
        self.total = int(placed["total_cents"])
        intent = post(client, f"{ORDERS_PATH}/{self.id}/pay", None)
        assert intent.status_code == 201
        self.intent_id = str(uuid.UUID(intent.json()["payment_intent_id"]))
        self._expire()

    def _expire(self) -> None:
        shop_psql(
            f"update orders set created_at = now() - interval '2 hours' where id = '{self.id}'"  # noqa: S608
        )
        compose("exec", "-T", "shop", "python", "-m", "app.order_expiration", "--once")
        assert self.status() == "expired"

    def status(self) -> str:
        return shop_psql(f"select status from orders where id = '{self.id}'")  # noqa: S608

    def pay_at_payment(self) -> int:
        """Le client lent paie quand même : confirmation directe chez payment (shop refuserait en 409)."""
        key = f"e2e-{uuid.uuid4().hex}"
        output = compose("exec", "-T", "shop", "python", "-c", CONFIRM_SCRIPT, self.intent_id, key)
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
        wait_for(
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
        wait_for(lambda: order.outbox_status() == "rejected_by_receiver", "événement non clos")

        reservations = shop_psql(
            f"select status from stock_reservations where order_id = '{order.id}'"  # noqa: S608
        ).split()
        assert reservations == ["released"]


class TestLedgerStaysConsistent:
    def test_the_ledger_check_is_green_after_the_automatic_refunds(self) -> None:
        result = run("exec", "-T", "payment", *LEDGER_CHECK)

        assert result.returncode == 0, result.stdout[-300:]
