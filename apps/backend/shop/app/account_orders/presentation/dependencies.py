from typing import cast

from fastapi import Request

from app.account_orders.application.get_my_order import GetMyOrderUseCase
from app.account_orders.application.link_guest_orders import LinkGuestOrdersUseCase
from app.account_orders.application.list_my_orders import ListMyOrdersUseCase


def get_list_my_orders_use_case(request: Request) -> ListMyOrdersUseCase:
    """Les cas d'usage sont cables dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(ListMyOrdersUseCase, request.app.state.list_my_orders_use_case)


def get_get_my_order_use_case(request: Request) -> GetMyOrderUseCase:
    return cast(GetMyOrderUseCase, request.app.state.get_my_order_use_case)


def get_link_guest_orders_use_case(request: Request) -> LinkGuestOrdersUseCase:
    return cast(LinkGuestOrdersUseCase, request.app.state.link_guest_orders_use_case)
