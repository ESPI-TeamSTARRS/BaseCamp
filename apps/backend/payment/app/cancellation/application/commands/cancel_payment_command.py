from dataclasses import dataclass


@dataclass(frozen=True)
class CancelPaymentCommand:
    caller: str
    intent_id: str
