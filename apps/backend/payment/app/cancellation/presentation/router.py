from typing import Annotated

from fastapi import APIRouter, Depends

from app.cancellation.application.cancellation_services import CancellationServices
from app.cancellation.application.commands.cancel_payment_command import CancelPaymentCommand
from app.cancellation.presentation.dependencies import get_cancellation_services
from app.intent.presentation.dependencies import get_calling_service
from app.intent.presentation.schemas.payment_intent_response import PaymentIntentResponse

router = APIRouter(prefix="/payments/intents", tags=["payment-cancellation"])

Services = Annotated[CancellationServices, Depends(get_cancellation_services)]
Caller = Annotated[str, Depends(get_calling_service)]


@router.post("/{intent_id}/cancel", response_model=PaymentIntentResponse)
def cancel_intent(intent_id: str, caller: Caller, services: Services) -> PaymentIntentResponse:
    view = services.cancel.execute(CancelPaymentCommand(caller=caller, intent_id=intent_id))
    return PaymentIntentResponse(**view.__dict__)
