from dataclasses import dataclass

REQUIRES_CONFIRMATION = "requires_confirmation"
SUCCEEDED = "succeeded"
FAILED = "failed"


@dataclass(frozen=True)
class PaymentAttempt:
    """Une tentative de paiement : une intention chez le fournisseur, une référence unique."""

    id: str
    order_id: str
    number: int
    reference: str
    intent_id: str
    status: str
