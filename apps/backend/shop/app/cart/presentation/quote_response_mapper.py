from app.cart.application.quote_cart import CartQuote
from app.cart.presentation.schemas.cart_quote_response import CartQuoteResponse
from app.cart.presentation.schemas.quote_line_response import QuoteLineResponse


class QuoteResponseMapper:
    @staticmethod
    def to_response(quote: CartQuote) -> CartQuoteResponse:
        return CartQuoteResponse(
            lines=[
                QuoteLineResponse(
                    product_id=line.product_id,
                    name=line.name,
                    unit_price_cents=line.unit_price_cents,
                    quantity=line.quantity,
                    line_total_cents=line.line_total_cents,
                    status=line.status.value,
                    available_quantity=line.available_quantity,
                )
                for line in quote.lines
            ],
            subtotal_cents=quote.subtotal_cents,
            shipping_cents=quote.shipping_cents,
            total_cents=quote.total_cents,
            free_shipping_threshold_cents=quote.free_shipping_threshold_cents,
            amount_remaining_for_free_shipping_cents=quote.amount_remaining_for_free_shipping_cents,
            has_issues=quote.has_issues,
        )
