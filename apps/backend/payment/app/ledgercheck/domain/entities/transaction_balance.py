from dataclasses import dataclass
from uuid import UUID

from app.ledgercheck.domain.entities.ledger_discrepancy import LedgerDiscrepancy
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind


@dataclass(frozen=True)
class TransactionBalance:
    """Totaux des débits et des crédits d'une transaction du grand livre."""

    transaction_id: UUID
    entry_count: int
    debit_cents: int
    credit_cents: int

    def discrepancy(self) -> LedgerDiscrepancy | None:
        if self.debit_cents == self.credit_cents:
            return None
        return LedgerDiscrepancy(
            DiscrepancyKind.TRANSACTION_UNBALANCED,
            self.transaction_id,
            self.debit_cents,
            self.credit_cents,
        )
