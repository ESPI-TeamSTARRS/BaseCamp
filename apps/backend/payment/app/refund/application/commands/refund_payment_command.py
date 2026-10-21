from dataclasses import dataclass


@dataclass(frozen=True)
class RefundPaymentCommand:
    caller: str
    idempotency_key: str
    intent_id: str
    amount: int
