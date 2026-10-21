from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.cart.application.invalid_cart_error import InvalidCartError
from app.pay.application.start_payment import StartPaymentUseCase
from app.pay.presentation.dependencies import get_start_payment_use_case
from app.pay.presentation.schemas.pay_request import PayRequest
from app.pay.presentation.schemas.pay_response import PayResponse

router = APIRouter(tags=["pay"])


@router.post("/pay", response_model=PayResponse, status_code=status.HTTP_201_CREATED)
def pay(
    request: PayRequest,
    use_case: Annotated[StartPaymentUseCase, Depends(get_start_payment_use_case)],
    idempotency_key: Annotated[str, Header(min_length=8, max_length=255)],
) -> PayResponse:
    items = [(line.product_id, line.quantity) for line in request.lines]
    try:
        intent = use_case.execute(request.order_reference, items, idempotency_key)
    except InvalidCartError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from None
    return PayResponse(
        payment_intent_id=intent.id,
        status=intent.status,
        amount_cents=intent.amount_cents,
        currency=intent.currency,
    )
