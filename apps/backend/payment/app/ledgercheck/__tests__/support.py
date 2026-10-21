"""Fabriques et doublures partagées par les tests de la tranche ledgercheck (pas un test)."""

from uuid import UUID, uuid4

from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.domain.entities.intent_ledger_position import IntentLedgerPosition
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance
from app.ledgercheck.domain.exceptions.ledger_read_error import LedgerReadError
from app.ledgercheck.domain.interfaces.ledger_reader import LedgerReader


def position(
    amount: int = 10000,
    refunded: int = 0,
    balance: int | None = None,
    status: IntentStatus = IntentStatus.SUCCEEDED,
    intent_id: UUID | None = None,
) -> IntentLedgerPosition:
    """Intention encaissée par défaut, au solde marchand sain sauf si `balance` est forcé."""
    healthy = amount - refunded if status is IntentStatus.SUCCEEDED else 0
    return IntentLedgerPosition(
        intent_id=intent_id or uuid4(),
        status=status,
        amount_cents=amount,
        refunded_cents=refunded,
        merchant_balance_cents=healthy if balance is None else balance,
    )


def balanced(amount: int = 10000, entries: int = 2) -> TransactionBalance:
    return TransactionBalance(uuid4(), entries, amount, amount)


class StubLedgerReader(LedgerReader):
    def __init__(self, snapshot: LedgerSnapshot | None = None, fail: bool = False) -> None:
        self._snapshot = snapshot or LedgerSnapshot((), ())
        self._fail = fail
        self.reads = 0

    def read_snapshot(self) -> LedgerSnapshot:
        self.reads += 1
        if self._fail:
            raise LedgerReadError
        return self._snapshot
