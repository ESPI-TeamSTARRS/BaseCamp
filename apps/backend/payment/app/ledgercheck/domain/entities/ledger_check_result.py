from dataclasses import dataclass

from app.ledgercheck.domain.entities.ledger_discrepancy import LedgerDiscrepancy


@dataclass(frozen=True)
class LedgerCheckResult:
    """Totaux contrôlés et écarts trouvés; cohérent si débits = crédits et aucun écart."""

    intents_checked: int
    transactions_checked: int
    entry_count: int
    debit_cents: int
    credit_cents: int
    discrepancies: tuple[LedgerDiscrepancy, ...]

    @property
    def discrepancy_count(self) -> int:
        return len(self.discrepancies)

    @property
    def is_consistent(self) -> bool:
        return not self.discrepancies and self.debit_cents == self.credit_cents
