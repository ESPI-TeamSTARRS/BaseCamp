from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount


@dataclass(frozen=True)
class LedgerEntry:
    """Une ligne du grand livre : immuable, jamais modifiée ni supprimée une fois écrite."""

    id: UUID
    transaction_id: UUID
    intent_id: UUID
    account: LedgerAccount
    direction: EntryDirection
    amount: Amount
    created_at: datetime
