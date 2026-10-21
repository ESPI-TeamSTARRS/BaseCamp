from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.order.application.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.order.application.insufficient_stock_error import InsufficientStockError
from app.order.application.invalid_order_error import InvalidOrderError
from app.order.application.place_order import PlaceOrderUseCase
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.presentation.dependencies import get_place_order_use_case
from app.order.presentation.order_response_mapper import OrderResponseMapper
from app.order.presentation.schemas.order_response import OrderResponse
from app.order.presentation.schemas.place_order_request import PlaceOrderRequest

router = APIRouter(tags=["orders"])


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def place_order(
    request: PlaceOrderRequest,
    response: Response,
    use_case: Annotated[PlaceOrderUseCase, Depends(get_place_order_use_case)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"),
    ],
) -> OrderResponse:
    address = request.shipping_address
    command = PlaceOrderCommand(
        idempotency_key=idempotency_key,
        email=request.email,
        full_name=address.full_name,
        address_line1=address.line1,
        address_line2=address.line2,
        postal_code=address.postal_code,
        city=address.city,
        country=address.country,
        items=tuple((line.product_id, line.quantity) for line in request.lines),
    )
    try:
        placed = use_case.execute(command)
    except InvalidOrderError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from None
    except IdempotencyKeyReusedError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from None
    except InsufficientStockError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.message) from None
    if not placed.created:
        response.status_code = status.HTTP_200_OK
    return OrderResponseMapper.to_response(placed)
