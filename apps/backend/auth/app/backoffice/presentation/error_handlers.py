from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.backoffice.application.backoffice_errors import (
    BackofficeRefusedError,
    FaceImageInvalidError,
    FaceTemplateInvalidError,
)
from app.login.domain.exceptions.domain_exception import DomainException

NO_STORE = {"Cache-Control": "no-store"}


def _respond(code: int) -> object:
    def handler(_: Request, error: Exception) -> JSONResponse:
        domain = cast(DomainException, error)
        return JSONResponse(status_code=code, content={"detail": domain.message}, headers=NO_STORE)

    return handler


def register_backoffice_error_handlers(application: FastAPI) -> None:
    """401 generique unique, 422 pour une image invalide, 409 pour un gabarit inexploitable."""
    application.add_exception_handler(
        BackofficeRefusedError,
        _respond(status.HTTP_401_UNAUTHORIZED),  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        FaceImageInvalidError,
        _respond(status.HTTP_422_UNPROCESSABLE_CONTENT),  # type: ignore[arg-type]
    )
    application.add_exception_handler(
        FaceTemplateInvalidError,
        _respond(status.HTTP_409_CONFLICT),  # type: ignore[arg-type]
    )
