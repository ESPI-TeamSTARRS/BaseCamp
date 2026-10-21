from pydantic import BaseModel


class PayResponse(BaseModel):
    payment_intent_id: str
    status: str
    amount_cents: int
    currency: str
