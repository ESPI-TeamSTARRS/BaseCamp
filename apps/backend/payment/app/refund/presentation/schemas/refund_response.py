from datetime import datetime

from pydantic import BaseModel


class RefundResponse(BaseModel):
    id: str
    payment_intent_id: str
    amount: int
    amount_refunded: int
    currency: str
    status: str
    created_at: datetime
