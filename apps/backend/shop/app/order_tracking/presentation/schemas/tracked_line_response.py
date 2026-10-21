from pydantic import BaseModel


class TrackedLineResponse(BaseModel):
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
