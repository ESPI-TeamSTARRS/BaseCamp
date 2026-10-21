from typing import cast

from fastapi import Request

from app.pay.application.start_payment import StartPaymentUseCase


def get_start_payment_use_case(request: Request) -> StartPaymentUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(StartPaymentUseCase, request.app.state.start_payment_use_case)
