from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentEvent:
    """Ce que le webhook de `payment` annonce : un fait sur une tentative, jamais une donnée de carte."""

    event_id: str
    event_type: str
    created_at: str | None
    reference: str | None
    amount_cents: int | None
    currency: str | None
    status: str | None
