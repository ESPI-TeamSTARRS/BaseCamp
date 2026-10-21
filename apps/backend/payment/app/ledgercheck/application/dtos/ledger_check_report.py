from dataclasses import dataclass

from app.ledgercheck.application.dtos.discrepancy_view import DiscrepancyView
from app.ledgercheck.domain.entities.ledger_check_result import LedgerCheckResult


@dataclass(frozen=True)
class LedgerCheckReport:
    """Résultat du contrôle, sans entité du domaine, pour la présentation."""

    is_consistent: bool
    intents_checked: int
    transactions_checked: int
    entry_count: int
    debit_cents: int
    credit_cents: int
    discrepancies: tuple[DiscrepancyView, ...]

    @property
    def discrepancy_count(self) -> int:
        return len(self.discrepancies)

    @classmethod
    def from_result(cls, result: LedgerCheckResult) -> "LedgerCheckReport":
        return cls(
            is_consistent=result.is_consistent,
            intents_checked=result.intents_checked,
            transactions_checked=result.transactions_checked,
            entry_count=result.entry_count,
            debit_cents=result.debit_cents,
            credit_cents=result.credit_cents,
            discrepancies=tuple(
                DiscrepancyView(
                    gap.kind.value, str(gap.resource_id), gap.expected_cents, gap.observed_cents
                )
                for gap in result.discrepancies
            ),
        )
