from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.payment_order_not_found_error import (
    PaymentOrderNotFoundError,
)
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.presentation.dependencies import (
    get_confirm_order_payment_use_case,
    get_request_order_payment_use_case,
)
from app.payment_request.presentation.schemas.confirm_payment_request import ConfirmPaymentRequest
from app.payment_request.presentation.schemas.confirm_payment_response import (
    ConfirmPaymentResponse,
)
from app.payment_request.presentation.schemas.pay_order_response import PayOrderResponse

router = APIRouter(tags=["payment-request"])


@router.post(
    "/orders/{order_id}/pay", response_model=PayOrderResponse, status_code=status.HTTP_201_CREATED
)
def pay_order(
    order_id: UUID,
    response: Response,
    use_case: Annotated[RequestOrderPaymentUseCase, Depends(get_request_order_payment_use_case)],
) -> PayOrderResponse:
    try:
        payment = use_case.execute(str(order_id))
    except PaymentOrderNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    except OrderNotPayableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.message) from None
    if not payment.created:
        response.status_code = status.HTTP_200_OK
    return PayOrderResponse(
        payment_intent_id=payment.intent.id,
        status=payment.intent.status,
        amount_cents=payment.intent.amount_cents,
        currency=payment.intent.currency,
        order_number=payment.order_number,
        payment_methods=list(payment.payment_methods),
    )


@router.post("/orders/{order_id}/pay/confirm", response_model=ConfirmPaymentResponse)
def confirm_order_payment(
    order_id: UUID,
    request: ConfirmPaymentRequest,
    use_case: Annotated[ConfirmOrderPaymentUseCase, Depends(get_confirm_order_payment_use_case)],
) -> ConfirmPaymentResponse:
    try:
        result = use_case.execute(str(order_id), request.payment_method)
    except PaymentOrderNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    except OrderNotPayableError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.message) from None
    return ConfirmPaymentResponse(
        order_number=result.order_number,
        order_status=result.order_status.value,
        payment_status=result.payment_status,
    )
