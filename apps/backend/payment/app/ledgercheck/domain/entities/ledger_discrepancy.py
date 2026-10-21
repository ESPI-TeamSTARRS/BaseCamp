from dataclasses import dataclass
from uuid import UUID

from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind


@dataclass(frozen=True)
class LedgerDiscrepancy:
    """Un écart entre ce que le grand livre devrait dire et ce qu'il dit.

    `resource_id` désigne l'intention (solde marchand) ou la transaction (déséquilibre). Pour une
    transaction, « attendu » porte les débits et « constaté » les crédits. Aucune autre donnée :
    ni référence de commande, ni appelant, ni clé.
    """

    kind: DiscrepancyKind
    resource_id: UUID
    expected_cents: int
    observed_cents: int
