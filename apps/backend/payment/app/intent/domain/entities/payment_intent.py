from dataclasses import dataclass, replace
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

    def can_be_confirmed(self, now: datetime) -> bool:
        """Une intention se confirme une fois, tant qu'elle attend sa confirmation et n'a pas expiré."""
        return self.status is IntentStatus.REQUIRES_CONFIRMATION and now < self.expires_at

    def succeed(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.SUCCEEDED)

    def fail(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.FAILED)
