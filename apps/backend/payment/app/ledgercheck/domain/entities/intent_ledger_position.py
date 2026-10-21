from dataclasses import dataclass
from uuid import UUID

from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.domain.entities.ledger_discrepancy import LedgerDiscrepancy
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind


@dataclass(frozen=True)
class IntentLedgerPosition:
    """Ce que l'état d'une intention annonce et ce que le grand livre porte pour elle.

    `merchant_balance_cents` est le solde du compte `marchand` de l'intention (crédits moins
    débits). Il doit valoir `capturé - remboursé` : seul un paiement `succeeded` a été capturé.
    """

    intent_id: UUID
    status: IntentStatus
    amount_cents: int
    refunded_cents: int
    merchant_balance_cents: int

    @property
    def captured_cents(self) -> int:
        return self.amount_cents if self.status is IntentStatus.SUCCEEDED else 0

    @property
    def expected_balance_cents(self) -> int:
        return self.captured_cents - self.refunded_cents

    def discrepancy(self) -> LedgerDiscrepancy | None:
        if self.merchant_balance_cents == self.expected_balance_cents:
            return None
        return LedgerDiscrepancy(
            DiscrepancyKind.INTENT_BALANCE,
            self.intent_id,
            self.expected_balance_cents,
            self.merchant_balance_cents,
        )
