from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.application.confirmation_services import ConfirmationServices
from app.confirmation.presentation.dependencies import get_confirmation_services
from app.confirmation.presentation.schemas.confirm_payment_request import ConfirmPaymentRequest
from app.intent.presentation.dependencies import get_calling_service
from app.intent.presentation.schemas.payment_intent_response import PaymentIntentResponse

router = APIRouter(prefix="/payments/intents", tags=["payment-confirmation"])

Services = Annotated[ConfirmationServices, Depends(get_confirmation_services)]
Caller = Annotated[str, Depends(get_calling_service)]


@router.post("/{intent_id}/confirm", response_model=PaymentIntentResponse)
def confirm_intent(
    intent_id: str,
    body: ConfirmPaymentRequest,
    caller: Caller,
    services: Services,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=255)],
) -> PaymentIntentResponse:
    view = services.confirm.execute(
        ConfirmPaymentCommand(
            caller=caller,
            idempotency_key=idempotency_key,
            intent_id=intent_id,
            payment_method=body.payment_method,
        )
    )
    return PaymentIntentResponse(**view.__dict__)
