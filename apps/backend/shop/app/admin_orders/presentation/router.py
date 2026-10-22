from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.admin_orders.application.admin_order_not_found_error import AdminOrderNotFoundError
from app.admin_orders.application.admin_views import AdminOrder
from app.admin_orders.application.get_admin_order import GetAdminOrderUseCase
from app.admin_orders.application.list_admin_orders import ListAdminOrdersUseCase
from app.admin_orders.presentation.dependencies import (
    get_admin_order_use_case,
    list_admin_orders_use_case,
)
from app.admin_orders.presentation.schemas.admin_order_list_response import (
    AdminOrderListResponse,
    AdminOrderSummaryResponse,
)
from app.admin_orders.presentation.schemas.admin_order_response import (
    AdminOrderLineResponse,
    AdminOrderResponse,
    AdminShippingAddressResponse,
)
from app.customer_identity.application.operator_view import Operator
from app.customer_identity.presentation.dependencies import current_operator

# Lecture seule : aucune route d'écriture. Réservée au rôle `operator` avec le second facteur `face`.
router = APIRouter(prefix="/admin/orders", tags=["orders-admin"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_SEARCH_LENGTH = 100
NO_STORE = "no-store"
CurrentOperator = Annotated[Operator, Depends(current_operator)]
OrderStatusFilter = Literal["pending_payment", "paid", "expired", "refunded"]


def _detail(order: AdminOrder) -> AdminOrderResponse:
    address = order.shipping_address
    return AdminOrderResponse(
        id=order.id,
        number=order.number,
        status=order.status,
        email=order.email,
        shipping_address=AdminShippingAddressResponse(
            full_name=address.full_name,
            line1=address.line1,
            line2=address.line2,
            postal_code=address.postal_code,
            city=address.city,
            country=address.country,
        ),
        lines=[
            AdminOrderLineResponse(
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


@router.get("", response_model=AdminOrderListResponse)
def list_orders(
    response: Response,
    operator: CurrentOperator,
    use_case: Annotated[ListAdminOrdersUseCase, Depends(list_admin_orders_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    order_status: Annotated[OrderStatusFilter | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
) -> AdminOrderListResponse:
    page = use_case.execute(operator.id, order_status, q.strip() if q else None, limit, offset)
    response.headers["Cache-Control"] = NO_STORE
    return AdminOrderListResponse(
        items=[
            AdminOrderSummaryResponse(
                id=item.id,
                number=item.number,
                status=item.status,
                email=item.email,
                total_cents=item.total_cents,
                item_count=item.item_count,
                created_at=item.created_at,
            )
            for item in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{order_id}", response_model=AdminOrderResponse)
def get_order(
    order_id: Annotated[UUID, Path()],
    response: Response,
    operator: CurrentOperator,
    use_case: Annotated[GetAdminOrderUseCase, Depends(get_admin_order_use_case)],
) -> AdminOrderResponse:
    try:
        order = use_case.execute(operator.id, str(order_id))
    except AdminOrderNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=error.message, headers={"Cache-Control": NO_STORE}
        ) from None
    response.headers["Cache-Control"] = NO_STORE
    return _detail(order)
