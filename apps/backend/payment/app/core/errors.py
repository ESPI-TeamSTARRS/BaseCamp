from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.correlation import CORRELATION_HEADER, current_correlation_id


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


def register_unhandled_error_handler(application: FastAPI, events: BusinessEventLogger) -> None:
    application.add_exception_handler(Exception, _unhandled(events))


def _database_unavailable(
    events: BusinessEventLogger,
) -> Callable[[Request, Exception], JSONResponse]:
    """Base injoignable ou pool épuisé : 503 générique, jamais le SQL ni l'hôte."""

    def handler(_: Request, __: Exception) -> JSONResponse:
        events.log(BusinessEvent.error(names.DATABASE_UNAVAILABLE, "database_unavailable"))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Service unavailable"},
            headers={"Retry-After": "1", CORRELATION_HEADER: current_correlation_id()},
        )

    return handler


def register_database_unavailable_handler(
    application: FastAPI, events: BusinessEventLogger
) -> None:
    application.add_exception_handler(OperationalError, _database_unavailable(events))
    application.add_exception_handler(PoolTimeoutError, _database_unavailable(events))
