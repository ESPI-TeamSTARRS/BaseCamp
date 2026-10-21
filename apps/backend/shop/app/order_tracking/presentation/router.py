from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.order_tracking.application.lookup_order import LookupOrderUseCase
from app.order_tracking.application.order_lookup_failed_error import OrderLookupFailedError
from app.order_tracking.presentation.dependencies import get_lookup_order_use_case
from app.order_tracking.presentation.schemas.order_lookup_request import OrderLookupRequest
from app.order_tracking.presentation.schemas.tracked_line_response import TrackedLineResponse
from app.order_tracking.presentation.schemas.tracked_order_response import TrackedOrderResponse

router = APIRouter(tags=["order-tracking"])


@router.post("/orders/lookup", response_model=TrackedOrderResponse)
def lookup_order(
    request: OrderLookupRequest,
    use_case: Annotated[LookupOrderUseCase, Depends(get_lookup_order_use_case)],
) -> TrackedOrderResponse:
    try:
        order = use_case.execute(request.order_number, request.email)
    except OrderLookupFailedError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    return TrackedOrderResponse(
        number=order.number,
        status=order.status,
        lines=[
            TrackedLineResponse(
                name=line.name,
                unit_price_cents=line.unit_price_cents,
                quantity=line.quantity,
                line_total_cents=line.line_total_cents,
            )
            for line in order.lines
        ],
        subtotal_cents=order.subtotal_cents,
        shipping_cents=order.shipping_cents,
        total_cents=order.total_cents,
        created_at=order.created_at,
    )
