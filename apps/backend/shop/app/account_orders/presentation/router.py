from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.account_orders.application.account_order_not_found_error import (
    AccountOrderNotFoundError,
)
from app.account_orders.application.account_views import AccountOrder
from app.account_orders.application.get_my_order import GetMyOrderUseCase
from app.account_orders.application.list_my_orders import MAX_PAGE_SIZE, ListMyOrdersUseCase
from app.account_orders.presentation.dependencies import (
    get_get_my_order_use_case,
    get_list_my_orders_use_case,
)
from app.account_orders.presentation.schemas.account_order_response import (
    AccountOrderLineResponse,
    AccountOrderPageResponse,
    AccountOrderResponse,
)
from app.customer_identity.application.customer_view import Customer
from app.customer_identity.presentation.dependencies import current_customer

NO_STORE = "no-store"

# Routes reservees aux clients connectes : sans jeton valide 401, cles illisibles 503.
router = APIRouter(prefix="/me", tags=["account-orders"])


def _response(order: AccountOrder) -> AccountOrderResponse:
    return AccountOrderResponse(
        id=order.id,
        number=order.number,
        status=order.status,
        lines=[
            AccountOrderLineResponse(
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


@router.get("/orders", response_model=AccountOrderPageResponse)
def list_my_orders(
    response: Response,
    customer: Annotated[Customer, Depends(current_customer)],
    use_case: Annotated[ListMyOrdersUseCase, Depends(get_list_my_orders_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountOrderPageResponse:
    page = use_case.execute(customer, limit, offset)
    response.headers["Cache-Control"] = NO_STORE
    return AccountOrderPageResponse(
        items=[_response(order) for order in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/orders/{order_id}", response_model=AccountOrderResponse)
def get_my_order(
    order_id: Annotated[UUID, Path()],
    response: Response,
    customer: Annotated[Customer, Depends(current_customer)],
    use_case: Annotated[GetMyOrderUseCase, Depends(get_get_my_order_use_case)],
) -> AccountOrderResponse:
    try:
        order = use_case.execute(customer, str(order_id))
    except AccountOrderNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    response.headers["Cache-Control"] = NO_STORE
    return _response(order)
