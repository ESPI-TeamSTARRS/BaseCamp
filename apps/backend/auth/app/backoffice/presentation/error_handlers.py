from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.backoffice.application.backoffice_errors import (
    BackofficeRefusedError,
    FaceImageInvalidError,
    FaceTemplateInvalidError,
)
from app.backoffice.application.invitation_errors import (
    InvitationPasswordError,
    InvitationPhotoError,
    InvitationRefusedError,
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


def _invitation_refused(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour jeton inconnu, expire, revoque ou utilise, adresse bloquee."""
    refused = cast(InvitationRefusedError, error)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": refused.message},
        headers=NO_STORE,
    )


def _invitation_unprocessable(_: Request, error: Exception) -> JSONResponse:
    """Mot de passe faible ou photos refusees : 422 avec un message fixe (jamais la saisie)."""
    invalid = cast(InvitationPasswordError | InvitationPhotoError, error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": invalid.message, "code": invalid.code},
        headers=NO_STORE,
    )


def register_invitation_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvitationRefusedError, _invitation_refused)
    application.add_exception_handler(InvitationPasswordError, _invitation_unprocessable)
    application.add_exception_handler(InvitationPhotoError, _invitation_unprocessable)
