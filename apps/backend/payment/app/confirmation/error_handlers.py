from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.confirmation.domain.exceptions.intent_not_confirmable_error import (
    IntentNotConfirmableError,
)


async def _not_confirmable(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Payment intent cannot be confirmed"},
    )


async def _key_reused(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Idempotency key already used with another request"},
    )


def register_confirmation_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(IntentNotConfirmableError, _not_confirmable)
    application.add_exception_handler(ConfirmationKeyReusedError, _key_reused)
