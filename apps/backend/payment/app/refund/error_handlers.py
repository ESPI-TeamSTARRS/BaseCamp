from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.refund.domain.exceptions.intent_not_refundable_error import IntentNotRefundableError
from app.refund.domain.exceptions.refund_exceeds_captured_error import RefundExceedsCapturedError
from app.refund.domain.exceptions.refund_key_reused_error import RefundKeyReusedError


async def _not_refundable(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Payment intent cannot be refunded"},
    )


async def _exceeds_captured(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Refund exceeds the captured amount"},
    )


async def _key_reused(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Idempotency key already used with another request"},
    )


def register_refund_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(IntentNotRefundableError, _not_refundable)
    application.add_exception_handler(RefundExceedsCapturedError, _exceeds_captured)
    application.add_exception_handler(RefundKeyReusedError, _key_reused)
