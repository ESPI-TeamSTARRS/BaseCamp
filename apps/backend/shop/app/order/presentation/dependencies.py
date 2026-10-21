from typing import cast

from fastapi import Request

from app.order.application.place_order import PlaceOrderUseCase


def get_place_order_use_case(request: Request) -> PlaceOrderUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(PlaceOrderUseCase, request.app.state.place_order_use_case)
