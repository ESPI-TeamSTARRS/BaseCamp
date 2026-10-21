from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request
from fastapi.responses import JSONResponse
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


@router.post(
    "/webhooks/payment",
    response_model=WebhookResponse,
    responses={409: {"description": "Paiement tardif sur une commande expirée : à rembourser"}},
)
async def receive_payment_webhook(
    request: Request,
    background: BackgroundTasks,
    receive: Annotated[ReceivePaymentWebhookUseCase, Depends(get_receive_payment_webhook_use_case)],
    send: Annotated[SendOrderConfirmationUseCase, Depends(get_send_order_confirmation_use_case)],
    signature: Annotated[str | None, Header(alias="X-Payment-Signature")] = None,
    event_id: Annotated[str | None, Header(alias="X-Payment-Event-Id")] = None,
) -> WebhookResponse | JSONResponse:
    """Webhook interne de `payment` : le corps brut est signé, il est donc lu avant tout décodage."""
    raw_body = await request.body()
    receipt = await run_in_threadpool(receive.execute, raw_body, signature, event_id)
    if receipt.mail is not None:
        background.add_task(
            send.execute, receipt.mail
        )  # après la réponse : un SMTP lent ne retarde pas payment
    if receipt.is_rejected:
        # 409 : payment rembourse le client (un 200 lui ferait croire la commande payée).
        return JSONResponse(
            status_code=409, content={"status": "rejected", "reason": receipt.reason}
        )
    return WebhookResponse.model_validate({"status": receipt.outcome.value})
