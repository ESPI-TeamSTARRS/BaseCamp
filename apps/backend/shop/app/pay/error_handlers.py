from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.pay.domain.exceptions.payment_rejected_error import PaymentRejectedError
from app.pay.domain.exceptions.payment_unavailable_error import PaymentUnavailableError

RETRY_AFTER_SECONDS = "5"


async def _payment_unavailable(_: Request, __: Exception) -> JSONResponse:
    """payment arrêté ou saturé : 503 propre, le reste de la boutique continue de répondre."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Paiement indisponible, reessayez plus tard."},
        headers={"Retry-After": RETRY_AFTER_SECONDS},
    )


async def _payment_rejected(_: Request, error: Exception) -> JSONResponse:
    conflict = isinstance(error, PaymentRejectedError) and error.conflict
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT if conflict else status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Paiement refuse."},
    )


def register_pay_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(PaymentUnavailableError, _payment_unavailable)
    application.add_exception_handler(PaymentRejectedError, _payment_rejected)
