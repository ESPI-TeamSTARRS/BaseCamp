"""Doublures de la confirmation de paiement : unité de travail en mémoire, envoi enregistreur, signature."""

import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from types import TracebackType
from typing import Any, Self

from app.order.domain.enums.order_status import OrderStatus
from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.mail_line import MailLine
from app.payment_confirmation.domain.entities.settlement_target import SettlementTarget
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.domain.errors.duplicate_webhook_event_error import (
    DuplicateWebhookEventError,
)
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender
from app.payment_confirmation.domain.interfaces.confirmation_unit_of_work import (
    ConfirmationUnitOfWork,
)
from app.payment_confirmation.domain.interfaces.settlement_targets import SettlementTargets
from app.payment_confirmation.domain.interfaces.webhook_events import WebhookEvents

SECRET = "whsec_test_test_test_test_test_test"  # noqa: S105 - valeur factice de test
NOW = 1790000000
ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"
ORDER_NUMBER = "BC-ABCDEFGHJK"
REFERENCE = "BC-ABCDEFGHJK"
ATTEMPT_ID = "a1111111-6c52-4d3b-8a52-1d6f7a9b2c10"
EVENT_ID = "0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11"
OTHER_EVENT_ID = "5c1c4b52-96a6-4d52-8f0b-6b0e1b2f7a33"
EMAIL = "camille.martin@example.org"
TOTAL_CENTS = 4490


@dataclass
class ConfirmationStore:
    targets: dict[str, SettlementTarget] = field(default_factory=dict)  # clé : référence
    events: dict[str, tuple[str, WebhookOutcome, str | None, str | None]] = field(
        default_factory=dict
    )
    confirmed_orders: set[str] = field(default_factory=set)
    committed_orders: list[str] = field(default_factory=list)
    attempt_statuses: dict[str, str] = field(default_factory=dict)
    commits: int = 0


def target(
    status: OrderStatus = OrderStatus.PENDING_PAYMENT,
    total_cents: int = TOTAL_CENTS,
    attempt_status: str = "requires_confirmation",
    refunded_cents: int = 0,
) -> SettlementTarget:
    return SettlementTarget(
        order_id=ORDER_ID,
        order_number=ORDER_NUMBER,
        order_status=status,
        total_cents=total_cents,
        attempt_id=ATTEMPT_ID,
        attempt_status=attempt_status,
        refunded_cents=refunded_cents,
    )


def store_with(status: OrderStatus = OrderStatus.PENDING_PAYMENT) -> ConfirmationStore:
    return ConfirmationStore(targets={REFERENCE: target(status)})


class _Events(WebhookEvents):
    def __init__(self, store: ConfirmationStore) -> None:
        self._store = store
        self.recorded: list[tuple[str, str, WebhookOutcome, str | None, str | None]] = []

    def exists(self, event_id: str) -> bool:
        return event_id in self._store.events

    def is_order_confirmed(self, order_id: str) -> bool:
        return order_id in self._store.confirmed_orders

    def record(
        self,
        event_id: str,
        event_type: str,
        outcome: WebhookOutcome,
        reason: str | None,
        confirmed_order_id: str | None,
    ) -> None:
        self.recorded.append((event_id, event_type, outcome, reason, confirmed_order_id))


class _Targets(SettlementTargets):
    def __init__(self, store: ConfirmationStore) -> None:
        self._store = store
        self.paid: list[str] = []
        self.statuses: dict[str, str] = {}
        self.committed: list[str] = []
        self.refunds: dict[str, int] = {}

    def find_for_update(self, reference: str) -> SettlementTarget | None:
        return self._store.targets.get(reference)

    def mark_paid(self, order_id: str) -> None:
        self.paid.append(order_id)

    def record_refund(self, order_id: str, refunded_cents: int) -> None:
        self.refunds[order_id] = refunded_cents

    def set_attempt_status(self, attempt_id: str, status: str) -> None:
        self.statuses[attempt_id] = status

    def commit_reservations(self, order_id: str) -> int:
        self.committed.append(order_id)
        return 1

    def mail_for(self, order_id: str) -> ConfirmationMail:
        return ConfirmationMail(
            to=EMAIL,
            order_number=ORDER_NUMBER,
            total_cents=TOTAL_CENTS,
            lines=(MailLine("Popote en titane", 1, 3900),),
        )


class FakeConfirmationUnitOfWork(ConfirmationUnitOfWork):
    events: _Events
    targets: _Targets

    def __init__(self, store: ConfirmationStore, duplicate_on_commit: bool = False) -> None:
        self._store = store
        self._duplicate = duplicate_on_commit
        self.events = _Events(store)
        self.targets = _Targets(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        if self._duplicate:
            raise DuplicateWebhookEventError
        self._store.commits += 1
        for event_id, event_type, outcome, reason, order_id in self.events.recorded:
            self._store.events[event_id] = (event_type, outcome, reason, order_id)
            if order_id is not None:
                self._store.confirmed_orders.add(order_id)
        self._store.committed_orders.extend(self.targets.committed)
        self._store.attempt_statuses.update(self.targets.statuses)
        for reference, current in list(self._store.targets.items()):
            if current.order_id in self.targets.paid:
                self._store.targets[reference] = replace(current, order_status=OrderStatus.PAID)
            if current.order_id in self.targets.refunds:
                refunded = self.targets.refunds[current.order_id]
                status = (
                    OrderStatus.REFUNDED
                    if refunded >= current.total_cents
                    else current.order_status
                )
                self._store.targets[reference] = replace(
                    current, order_status=status, refunded_cents=refunded
                )


class RecordingSender(ConfirmationSender):
    def __init__(self, failing: bool = False) -> None:
        self.sent: list[ConfirmationMail] = []
        self._failing = failing

    def send(self, mail: ConfirmationMail) -> None:
        if self._failing:
            raise ConfirmationDeliveryError
        self.sent.append(mail)


def event_body(**overrides: Any) -> bytes:
    """Corps tel que `payment` le publie (JSON compact, ce sont ces octets qui sont signés)."""
    document: dict[str, Any] = {
        "id": EVENT_ID,
        "type": "payment.succeeded",
        "created_at": "2026-10-21T09:00:00.123Z",
        "data": {
            "payment_intent_id": "7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42",
            "order_reference": REFERENCE,
            "amount": TOTAL_CENTS,
            "currency": "EUR",
            "status": "succeeded",
        },
    }
    document.update(overrides)
    return json.dumps(document, separators=(",", ":")).encode()


def sign(body: bytes, secret: str = SECRET, timestamp: int = NOW) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"
