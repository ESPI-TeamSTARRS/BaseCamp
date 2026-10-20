from pydantic import BaseModel, ConfigDict, Field

from app.cart.presentation.schemas.cart_line_request import CartLineRequest


class CartQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[CartLineRequest] = Field(min_length=1, max_length=50)
