from typing import cast

from fastapi import Request

from app.catalog.application.list_products import ListProductsUseCase


def get_list_products_use_case(request: Request) -> ListProductsUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(ListProductsUseCase, request.app.state.list_products_use_case)
