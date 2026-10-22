from typing import cast

from fastapi import Request

from app.admin_orders.application.get_admin_order import GetAdminOrderUseCase
from app.admin_orders.application.list_admin_orders import ListAdminOrdersUseCase


def list_admin_orders_use_case(request: Request) -> ListAdminOrdersUseCase:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(ListAdminOrdersUseCase, request.app.state.list_admin_orders_use_case)


def get_admin_order_use_case(request: Request) -> GetAdminOrderUseCase:
    return cast(GetAdminOrderUseCase, request.app.state.get_admin_order_use_case)
