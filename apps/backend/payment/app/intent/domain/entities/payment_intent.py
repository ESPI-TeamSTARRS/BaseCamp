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

    def is_overdue(self, now: datetime) -> bool:
        """L'échéance est atteinte (l'instant d'échéance lui-même compte comme dépassé)."""
        return now >= self.expires_at

    def can_be_canceled(self, now: datetime) -> bool:
        """Seule une intention encore en attente de confirmation, dans son délai, s'annule."""
        return self.status is IntentStatus.REQUIRES_CONFIRMATION and not self.is_overdue(now)

    def cancel(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.CANCELED)

    def expire(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.EXPIRED)

    def succeed(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.SUCCEEDED)

    def fail(self) -> "PaymentIntent":
        return replace(self, status=IntentStatus.FAILED)

    def can_be_refunded(self) -> bool:
        """Seule une intention encaissée (`succeeded`) se rembourse."""
        return self.status is IntentStatus.SUCCEEDED

    @property
    def refundable_cents(self) -> int:
        """Ce qui reste remboursable : le montant capturé moins ce qui a déjà été rendu."""
        return self.amount.cents - self.refunded_amount

    def refund(self, amount: Amount) -> "PaymentIntent":
        if amount.cents > self.refundable_cents:
            raise ValueError("amount exceeds the refundable amount")
        return replace(self, refunded_amount=self.refunded_amount + amount.cents)
