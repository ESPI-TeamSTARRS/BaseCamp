from dataclasses import dataclass

from app.ledgercheck.application.check_ledger_consistency import CheckLedgerConsistencyUseCase
from app.ledgercheck.application.read_ledger_discrepancy_count import ReadLedgerDiscrepancyCount


@dataclass(frozen=True)
class LedgerCheckServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la commande et les métriques."""

    check: CheckLedgerConsistencyUseCase
    discrepancy_count: ReadLedgerDiscrepancyCount
