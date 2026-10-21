from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from starlette.concurrency import run_in_threadpool

from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.application.send_order_confirmation import (
    SendOrderConfirmationUseCase,
)
from app.payment_confirmation.presentation.dependencies import (
    get_receive_payment_webhook_use_case,
    get_send_order_confirmation_use_case,
)
from app.payment_confirmation.presentation.schemas.webhook_response import WebhookResponse

router = APIRouter(tags=["payment-confirmation"])


@router.post("/webhooks/payment", response_model=WebhookResponse)
async def receive_payment_webhook(
    request: Request,
    background: BackgroundTasks,
    receive: Annotated[ReceivePaymentWebhookUseCase, Depends(get_receive_payment_webhook_use_case)],
    send: Annotated[SendOrderConfirmationUseCase, Depends(get_send_order_confirmation_use_case)],
    signature: Annotated[str | None, Header(alias="X-Payment-Signature")] = None,
    event_id: Annotated[str | None, Header(alias="X-Payment-Event-Id")] = None,
) -> WebhookResponse:
    """Webhook interne de `payment` : le corps brut est signé, il est donc lu avant tout décodage."""
    raw_body = await request.body()
    receipt = await run_in_threadpool(receive.execute, raw_body, signature, event_id)
    if receipt.mail is not None:
        background.add_task(
            send.execute, receipt.mail
        )  # après la réponse : un SMTP lent ne retarde pas payment
    return WebhookResponse(status=receipt.outcome.value)
