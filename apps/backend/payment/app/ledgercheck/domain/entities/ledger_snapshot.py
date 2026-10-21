from collections.abc import Sequence
from dataclasses import dataclass

from app.ledgercheck.domain.entities.intent_ledger_position import IntentLedgerPosition
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance


@dataclass(frozen=True)
class LedgerSnapshot:
    """Lecture cohérente (un seul instant) des intentions et des transactions du grand livre."""

    positions: Sequence[IntentLedgerPosition]
    transactions: Sequence[TransactionBalance]
