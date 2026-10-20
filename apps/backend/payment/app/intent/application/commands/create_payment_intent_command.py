from dataclasses import dataclass


@dataclass(frozen=True)
class CreatePaymentIntentCommand:
    caller: str
    idempotency_key: str
    order_reference: str
    amount: int
    currency: str
