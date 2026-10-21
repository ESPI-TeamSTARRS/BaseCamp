from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.payment_confirmation.domain.errors.invalid_webhook_payload_error import (
    InvalidWebhookPayloadError,
)
from app.payment_confirmation.domain.errors.invalid_webhook_signature_error import (
    InvalidWebhookSignatureError,
)


async def _invalid_signature(_: Request, __: Exception) -> JSONResponse:
    """Signature fausse, absente ou hors fenêtre : 401 sans dire laquelle (le motif est dans le journal)."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "Signature invalide."}
    )


async def _invalid_payload(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "Evenement invalide."}
    )


def register_payment_confirmation_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvalidWebhookSignatureError, _invalid_signature)
    application.add_exception_handler(InvalidWebhookPayloadError, _invalid_payload)
