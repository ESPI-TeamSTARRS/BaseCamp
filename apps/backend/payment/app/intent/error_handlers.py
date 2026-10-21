from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.intent.domain.exceptions.amount_exceeds_limit_error import AmountExceedsLimitError
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError


def _json(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _validation_error(
    events: BusinessEventLogger,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(_: Request, error: Exception) -> JSONResponse:
        events.log(BusinessEvent.denied("service.request_rejected", "invalid_request"))
        return _validation_response(error)

    return handler


def _validation_response(error: Exception) -> JSONResponse:
    """422 assaini : seuls le champ et le code d'erreur sont renvoyés, jamais la valeur reçue."""
    validation_error = cast(RequestValidationError, error)
    fields = [
        {"field": ".".join(str(part) for part in item["loc"][1:]), "code": item["type"]}
        for item in validation_error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request", "errors": fields},
    )


async def _key_reused(_: Request, __: Exception) -> JSONResponse:
    return _json(422, "Idempotency key already used with another request")


async def _amount_too_high(_: Request, __: Exception) -> JSONResponse:
    return _json(422, "Amount above the allowed limit")


async def _duplicate_order(_: Request, __: Exception) -> JSONResponse:
    return _json(status.HTTP_409_CONFLICT, "A payment intent already exists for this order")


async def _not_found(_: Request, __: Exception) -> JSONResponse:
    return _json(status.HTTP_404_NOT_FOUND, "Not found")


def register_error_handlers(application: FastAPI, events: BusinessEventLogger) -> None:
    application.add_exception_handler(RequestValidationError, _validation_error(events))
    application.add_exception_handler(IdempotencyKeyReusedError, _key_reused)
    application.add_exception_handler(AmountExceedsLimitError, _amount_too_high)
    application.add_exception_handler(DuplicateOrderReferenceError, _duplicate_order)
    application.add_exception_handler(PaymentIntentNotFoundError, _not_found)
