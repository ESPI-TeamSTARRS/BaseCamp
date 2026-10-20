from typing import cast

from fastapi import Request

from app.cart.application.quote_cart import QuoteCartUseCase


def get_quote_cart_use_case(request: Request) -> QuoteCartUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(QuoteCartUseCase, request.app.state.quote_cart_use_case)
