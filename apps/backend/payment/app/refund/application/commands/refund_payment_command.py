from dataclasses import dataclass


@dataclass(frozen=True)
class RefundPaymentCommand:
    caller: str
    idempotency_key: str
    intent_id: str
    amount: int
    actor_type: str = "service"  # `operator` quand un humain rembourse (identite dans `caller`)
