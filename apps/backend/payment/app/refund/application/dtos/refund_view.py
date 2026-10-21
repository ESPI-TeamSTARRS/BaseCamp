from dataclasses import dataclass
from datetime import UTC, datetime

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.refund.domain.entities.refund import Refund


@dataclass(frozen=True)
class RefundView:
    """Vue d'un remboursement exposée à la présentation (types primitifs)."""

    id: str
    payment_intent_id: str
    amount: int
    amount_refunded: int
    currency: str
    status: str
    created_at: datetime

    @classmethod
    def from_entities(cls, refund: Refund, intent: PaymentIntent) -> "RefundView":
        return cls(
            id=str(refund.id),
            payment_intent_id=str(refund.intent_id),
            amount=refund.amount.cents,
            amount_refunded=refund.amount_refunded,
            currency=intent.currency.value,
            status="succeeded",
            created_at=refund.created_at.astimezone(UTC),
        )
