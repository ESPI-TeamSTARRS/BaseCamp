from app.ledgercheck.domain.entities.ledger_check_result import LedgerCheckResult
from app.ledgercheck.domain.entities.ledger_discrepancy import LedgerDiscrepancy
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot


class LedgerAuditor:
    """Compare le grand livre à l'état des paiements : règle pure, sans accès à la base.

    Deux contrôles : le solde marchand de chaque intention vaut `capturé - remboursé`, et chaque
    transaction a autant de débits que de crédits. Les écarts sortent dans un ordre stable (soldes
    d'intention puis transactions, chacun par identifiant) pour que deux passages se comparent.
    """

    def audit(self, snapshot: LedgerSnapshot) -> LedgerCheckResult:
        intent_gaps = [d for p in snapshot.positions if (d := p.discrepancy())]
        transaction_gaps = [d for t in snapshot.transactions if (d := t.discrepancy())]
        return LedgerCheckResult(
            intents_checked=len(snapshot.positions),
            transactions_checked=len(snapshot.transactions),
            entry_count=sum(t.entry_count for t in snapshot.transactions),
            debit_cents=sum(t.debit_cents for t in snapshot.transactions),
            credit_cents=sum(t.credit_cents for t in snapshot.transactions),
            discrepancies=(*self._ordered(intent_gaps), *self._ordered(transaction_gaps)),
        )

    @staticmethod
    def _ordered(gaps: list[LedgerDiscrepancy]) -> list[LedgerDiscrepancy]:
        return sorted(gaps, key=lambda gap: gap.resource_id.int)
