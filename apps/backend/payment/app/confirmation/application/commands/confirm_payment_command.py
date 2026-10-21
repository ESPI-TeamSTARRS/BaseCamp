from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmPaymentCommand:
    caller: str
    idempotency_key: str
    intent_id: str
    payment_method: str
