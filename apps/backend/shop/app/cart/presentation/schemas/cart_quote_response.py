from pydantic import BaseModel

from app.cart.presentation.schemas.quote_line_response import QuoteLineResponse


class CartQuoteResponse(BaseModel):
    lines: list[QuoteLineResponse]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    free_shipping_threshold_cents: int
    amount_remaining_for_free_shipping_cents: int
    has_issues: bool
