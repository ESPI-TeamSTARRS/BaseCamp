from dataclasses import dataclass

from app.pay.domain.entities.payment_intent_ref import PaymentIntentRef


@dataclass(frozen=True)
class OrderPayment:
    """Intention à confirmer côté client; created=False pour un rejeu."""

    order_number: str
    intent: PaymentIntentRef
    created: bool
    payment_methods: tuple[str, ...]
