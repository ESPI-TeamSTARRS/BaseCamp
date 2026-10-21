from typing import cast

from fastapi import Request

from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase


def get_request_order_payment_use_case(request: Request) -> RequestOrderPaymentUseCase:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(RequestOrderPaymentUseCase, request.app.state.request_order_payment_use_case)


def get_confirm_order_payment_use_case(request: Request) -> ConfirmOrderPaymentUseCase:
    return cast(ConfirmOrderPaymentUseCase, request.app.state.confirm_order_payment_use_case)
