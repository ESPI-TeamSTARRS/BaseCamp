from pydantic import BaseModel


class ConfirmPaymentResponse(BaseModel):
    order_number: str
    order_status: str
    payment_status: str
