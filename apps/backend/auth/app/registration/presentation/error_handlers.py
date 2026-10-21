from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.registration.application.invalid_registration_error import InvalidRegistrationError
from app.registration.application.invalid_verification_token_error import (
    InvalidVerificationTokenError,
)

INVALID_REQUEST = "Requete invalide."


def _invalid_registration(_: Request, error: Exception) -> JSONResponse:
    """Champs fautifs et messages fixes : la valeur saisie n'est jamais renvoyee."""
    invalid = cast(InvalidRegistrationError, error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": INVALID_REQUEST,
            "fields": list(invalid.fields),
            "messages": list(invalid.messages),
        },
    )


def _invalid_verification_token(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour jeton inconnu, expire ou deja utilise."""
    invalid = cast(InvalidVerificationTokenError, error)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": invalid.message}
    )


def register_registration_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvalidRegistrationError, _invalid_registration)
    application.add_exception_handler(InvalidVerificationTokenError, _invalid_verification_token)
