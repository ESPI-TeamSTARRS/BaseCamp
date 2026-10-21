from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentIntentRef:
    """Intention de paiement telle que la boutique la connaît : identifiant, statut, montant."""

    id: str
    status: str
    amount_cents: int
    currency: str
