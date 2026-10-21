from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.cancellation.domain.exceptions.intent_not_cancelable_error import (
    IntentNotCancelableError,
)


async def _not_cancelable(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Payment intent cannot be canceled"},
    )


def register_cancellation_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(IntentNotCancelableError, _not_cancelable)
