from pydantic import BaseModel


class QuoteLineResponse(BaseModel):
    product_id: str
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    status: str
    available_quantity: int
