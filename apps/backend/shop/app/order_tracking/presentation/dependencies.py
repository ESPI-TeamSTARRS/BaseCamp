from typing import cast

from fastapi import Request

from app.order_tracking.application.lookup_order import LookupOrderUseCase


def get_lookup_order_use_case(request: Request) -> LookupOrderUseCase:
    """Le cas d'usage est câblé dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(LookupOrderUseCase, request.app.state.lookup_order_use_case)
