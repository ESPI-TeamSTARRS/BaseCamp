from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.backoffice.application.backoffice_errors import (
    BackofficeRefusedError,
    FaceImageInvalidError,
    FaceTemplateInvalidError,
)

NO_STORE = {"Cache-Control": "no-store"}


def _refused(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour defi inconnu, expire ou utilise, visage refuse, mot de passe faux,
    etape verrouillee ou compte sans droit."""
    refused = cast(BackofficeRefusedError, error)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": refused.message},
        headers=NO_STORE,
    )


def _invalid_image(_: Request, error: Exception) -> JSONResponse:
    """Image invalide : erreur du client, jamais un echec compte."""
    invalid = cast(FaceImageInvalidError, error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": invalid.message},
        headers=NO_STORE,
    )


def _invalid_template(_: Request, error: Exception) -> JSONResponse:
    """Gabarit inexploitable : 409, journalise cote service."""
    invalid = cast(FaceTemplateInvalidError, error)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": invalid.message},
        headers=NO_STORE,
    )


def register_backoffice_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(BackofficeRefusedError, _refused)
    application.add_exception_handler(FaceImageInvalidError, _invalid_image)
    application.add_exception_handler(FaceTemplateInvalidError, _invalid_template)
