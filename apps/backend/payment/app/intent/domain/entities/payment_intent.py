from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.value_objects.amount import Amount


@dataclass(frozen=True)
class PaymentIntent:
    id: UUID
    order_reference: str
    amount: Amount
    currency: Currency
    status: IntentStatus
    refunded_amount: int
    expires_at: datetime
    created_at: datetime

    @classmethod
    def create(
        cls, order_reference: str, amount: Amount, currency: Currency, now: datetime, ttl: timedelta
    ) -> "PaymentIntent":
        return cls(
            id=uuid4(),
            order_reference=order_reference,
            amount=amount,
            currency=currency,
            status=IntentStatus.REQUIRES_CONFIRMATION,
            refunded_amount=0,
            expires_at=now + ttl,
            created_at=now,
        )
