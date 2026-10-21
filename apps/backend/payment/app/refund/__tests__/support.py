"""Doublures en mémoire du remboursement, partagées par les tests de cas d'usage (pas un test)."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.refund.domain.entities.refund import Refund
from app.refund.domain.interfaces.refund_session import RefundSession
from app.refund.domain.interfaces.refund_unit_of_work import RefundUnitOfWork
from app.webhook.domain.entities.outbox_event import OutboxEvent


class InMemoryStore:
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.refunds: dict[tuple[str, str], Refund] = {}
        self.ledger: list[LedgerTransaction] = []
        self.outbox: list[OutboxEvent] = []


class InMemorySession(RefundSession):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        return self._store.intents.get(intent_id)

    def find_refund(self, caller: str, key: str) -> Refund | None:
        return self._store.refunds.get((caller, key))

    def save(
        self,
        intent: PaymentIntent,
        refund: Refund,
        ledger: LedgerTransaction,
        outbox_event: OutboxEvent,
    ) -> None:
        self._store.intents[intent.id] = intent
        self._store.refunds[(refund.caller, refund.key)] = refund
        self._store.ledger.append(ledger)
        self._store.outbox.append(outbox_event)


class InMemoryUnitOfWork(RefundUnitOfWork):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    @contextmanager
    def begin(self) -> Iterator[RefundSession]:
        yield InMemorySession(self._store)
