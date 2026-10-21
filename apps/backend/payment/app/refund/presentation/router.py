from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.caller_identity.application.caller_view import Caller as AuthenticatedCaller
from app.intent.presentation.dependencies import get_refund_caller
from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.application.refund_services import RefundServices
from app.refund.presentation.dependencies import get_refund_services
from app.refund.presentation.logged_validation_route import LoggedValidationRoute
from app.refund.presentation.schemas.refund_request import RefundRequest
from app.refund.presentation.schemas.refund_response import RefundResponse

router = APIRouter(
    prefix="/payments/intents", tags=["payment-refunds"], route_class=LoggedValidationRoute
)

Services = Annotated[RefundServices, Depends(get_refund_services)]
Caller = Annotated[AuthenticatedCaller, Depends(get_refund_caller)]


@router.post(
    "/{intent_id}/refunds",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
)
def refund_intent(
    intent_id: str,
    body: RefundRequest,
    response: Response,
    caller: Caller,
    services: Services,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=255)],
) -> RefundResponse:
    view = services.refund.execute(
        RefundPaymentCommand(
            caller=caller.subject,
            actor_type=caller.actor_type,
            idempotency_key=idempotency_key,
            intent_id=intent_id,
            amount=body.amount,
        )
    )
    if view.replayed:
        response.status_code = status.HTTP_200_OK
    return RefundResponse(
        id=view.id,
        payment_intent_id=view.payment_intent_id,
        amount=view.amount,
        amount_refunded=view.amount_refunded,
        currency=view.currency,
        status=view.status,
        created_at=view.created_at,
    )
