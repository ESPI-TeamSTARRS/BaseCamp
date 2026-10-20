from collections.abc import Callable
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.correlation import CORRELATION_HEADER, current_correlation_id

EXTRA_FORBIDDEN = "extra_forbidden"


def _invalid_request(events: BusinessEventLogger) -> Callable[[Request, Exception], JSONResponse]:
    def handler(_: Request, error: Exception) -> JSONResponse:
        events.log(BusinessEvent.denied("service.request_rejected", "invalid_request"))
        return _invalid_request_response(error)

    return handler


def _invalid_request_response(error: Exception) -> JSONResponse:
    """422 assaini : on nomme au plus les champs declares fautifs, jamais une valeur ni une cle recue."""
    errors = cast(RequestValidationError, error).errors()
    fields = sorted(
        {
            str(item["loc"][-1])
            for item in errors
            if item["loc"] and item["type"] != EXTRA_FORBIDDEN and isinstance(item["loc"][-1], str)
        }
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "Requete invalide.", "fields": fields},
    )


def _unhandled(events: BusinessEventLogger) -> Callable[[Request, Exception], JSONResponse]:
    """500 generique : ni trace ni message d'exception cote client, un evenement `error` cote logs."""

    def handler(_: Request, __: Exception) -> JSONResponse:
        events.log(BusinessEvent.error("service.unhandled_error", "internal_error"))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Erreur interne."},
            headers={CORRELATION_HEADER: current_correlation_id()},
        )

    return handler


def register_error_handlers(application: FastAPI, events: BusinessEventLogger) -> None:
    application.add_exception_handler(RequestValidationError, _invalid_request(events))
    application.add_exception_handler(Exception, _unhandled(events))
