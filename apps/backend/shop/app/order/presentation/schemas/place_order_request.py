from pydantic import BaseModel, ConfigDict, Field

from app.order.presentation.schemas.order_line_request import OrderLineRequest
from app.order.presentation.schemas.shipping_address_request import ShippingAddressRequest

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class PlaceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    shipping_address: ShippingAddressRequest = Field(alias="shippingAddress")
    lines: list[OrderLineRequest] = Field(min_length=1, max_length=50)
