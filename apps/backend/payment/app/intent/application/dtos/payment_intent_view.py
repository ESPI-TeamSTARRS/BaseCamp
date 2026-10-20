from dataclasses import dataclass
from datetime import UTC, datetime

from app.intent.domain.entities.payment_intent import PaymentIntent


@dataclass(frozen=True)
class PaymentIntentView:
    """Vue de lecture d'une intention, exposée à la présentation (types primitifs)."""

    id: str
    order_reference: str
    amount: int
    currency: str
    status: str
    refunded_amount: int
    expires_at: datetime
    created_at: datetime

    @classmethod
    def from_entity(cls, intent: PaymentIntent) -> "PaymentIntentView":
        return cls(
            id=str(intent.id),
            order_reference=intent.order_reference,
            amount=intent.amount.cents,
            currency=intent.currency.value,
            status=intent.status.value,
            refunded_amount=intent.refunded_amount,
            expires_at=intent.expires_at.astimezone(UTC),
            created_at=intent.created_at.astimezone(UTC),
        )
