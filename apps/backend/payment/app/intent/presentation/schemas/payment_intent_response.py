from datetime import datetime

from pydantic import BaseModel


class PaymentIntentResponse(BaseModel):
    id: str
    order_reference: str
    amount: int
    currency: str
    status: str
    refunded_amount: int
    expires_at: datetime
    created_at: datetime
