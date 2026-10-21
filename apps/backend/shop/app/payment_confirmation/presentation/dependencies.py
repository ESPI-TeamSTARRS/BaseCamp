from typing import cast

from fastapi import Request

from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.application.send_order_confirmation import (
    SendOrderConfirmationUseCase,
)


def get_receive_payment_webhook_use_case(request: Request) -> ReceivePaymentWebhookUseCase:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(ReceivePaymentWebhookUseCase, request.app.state.receive_payment_webhook_use_case)


def get_send_order_confirmation_use_case(request: Request) -> SendOrderConfirmationUseCase:
    return cast(SendOrderConfirmationUseCase, request.app.state.send_order_confirmation_use_case)
