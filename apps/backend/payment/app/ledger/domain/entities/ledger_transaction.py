from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.entities.ledger_entry import LedgerEntry
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount
from app.ledger.domain.exceptions.unbalanced_transaction_error import UnbalancedTransactionError


@dataclass(frozen=True)
class LedgerTransaction:
    """Écritures posées ensemble en double entrée : débits égaux aux crédits, sinon refusée."""

    id: UUID
    entries: tuple[LedgerEntry, ...]

    def __post_init__(self) -> None:
        if any(entry.transaction_id != self.id for entry in self.entries):
            raise UnbalancedTransactionError
        debits = self._total(EntryDirection.DEBIT)
        credits_ = self._total(EntryDirection.CREDIT)
        if debits == 0 or debits != credits_:
            raise UnbalancedTransactionError

    def _total(self, direction: EntryDirection) -> int:
        return sum(entry.amount.cents for entry in self.entries if entry.direction is direction)

    @classmethod
    def payment_received(
        cls, intent_id: UUID, amount: Amount, now: datetime
    ) -> "LedgerTransaction":
        """Paiement encaissé : débit du compte d'attente du client, crédit du marchand."""
        transaction_id = uuid4()
        return cls(
            transaction_id,
            (
                LedgerEntry(
                    uuid4(),
                    transaction_id,
                    intent_id,
                    LedgerAccount.CLIENT_ATTENTE,
                    EntryDirection.DEBIT,
                    amount,
                    now,
                ),
                LedgerEntry(
                    uuid4(),
                    transaction_id,
                    intent_id,
                    LedgerAccount.MARCHAND,
                    EntryDirection.CREDIT,
                    amount,
                    now,
                ),
            ),
        )
