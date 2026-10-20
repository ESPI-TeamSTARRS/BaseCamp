from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.cart.application.invalid_cart_error import InvalidCartError
from app.cart.application.quote_cart import QuoteCartUseCase
from app.cart.presentation.dependencies import get_quote_cart_use_case
from app.cart.presentation.quote_response_mapper import QuoteResponseMapper
from app.cart.presentation.schemas.cart_quote_request import CartQuoteRequest
from app.cart.presentation.schemas.cart_quote_response import CartQuoteResponse

router = APIRouter(tags=["cart"])


@router.post("/cart/quote", response_model=CartQuoteResponse)
def quote_cart(
    request: CartQuoteRequest,
    use_case: Annotated[QuoteCartUseCase, Depends(get_quote_cart_use_case)],
) -> CartQuoteResponse:
    items = [(line.product_id, line.quantity) for line in request.lines]
    try:
        quote = use_case.execute(items)
    except InvalidCartError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from None
    return QuoteResponseMapper.to_response(quote)
