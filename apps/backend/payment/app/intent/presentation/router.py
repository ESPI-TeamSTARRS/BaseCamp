from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.intent.application.commands.create_payment_intent_command import (
    CreatePaymentIntentCommand,
)
from app.intent.application.dtos.payment_intent_view import PaymentIntentView
from app.intent.application.intent_services import IntentServices
from app.intent.presentation.dependencies import get_calling_service, get_intent_services
from app.intent.presentation.schemas.create_payment_intent_request import (
    CreatePaymentIntentRequest,
)
from app.intent.presentation.schemas.payment_intent_response import PaymentIntentResponse
from app.ratelimit.application.rate_limit_routes import ROUTE_INTENTS_CREATE, ROUTE_INTENTS_READ
from app.ratelimit.presentation.dependencies import rate_limited

router = APIRouter(prefix="/payments/intents", tags=["payment-intents"])
CreateLimit = Depends(rate_limited(ROUTE_INTENTS_CREATE, get_calling_service))
ReadLimit = Depends(rate_limited(ROUTE_INTENTS_READ, get_calling_service))

Services = Annotated[IntentServices, Depends(get_intent_services)]
Caller = Annotated[str, Depends(get_calling_service)]


def _to_response(view: PaymentIntentView) -> PaymentIntentResponse:
    return PaymentIntentResponse(**view.__dict__)


@router.post(
    "",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CreateLimit],
)
def create_intent(
    body: CreatePaymentIntentRequest,
    response: Response,
    caller: Caller,
    services: Services,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=255)],
) -> PaymentIntentResponse:
    command = CreatePaymentIntentCommand(
        caller=caller,
        idempotency_key=idempotency_key,
        order_reference=body.order_reference,
        amount=body.amount,
        currency=body.currency,
    )
    result = services.create.execute(command)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return _to_response(result.intent)


@router.get("", response_model=PaymentIntentResponse, dependencies=[ReadLimit])
def get_intent_by_order(
    order_reference: Annotated[str, Query(max_length=64)],
    _caller: Caller,
    services: Services,
) -> PaymentIntentResponse:
    return _to_response(services.get_by_order.execute(order_reference))


@router.get("/{intent_id}", response_model=PaymentIntentResponse, dependencies=[ReadLimit])
def get_intent(intent_id: str, _caller: Caller, services: Services) -> PaymentIntentResponse:
    return _to_response(services.get_by_id.execute(intent_id))
