from datetime import datetime

from pydantic import BaseModel

from app.order.presentation.schemas.order_line_response import OrderLineResponse
from app.order.presentation.schemas.shipping_address_response import ShippingAddressResponse


class OrderResponse(BaseModel):
    id: str
    number: str
    status: str
    email: str
    shipping_address: ShippingAddressResponse
    lines: list[OrderLineResponse]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
