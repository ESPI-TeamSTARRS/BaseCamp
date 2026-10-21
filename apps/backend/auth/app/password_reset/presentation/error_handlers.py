from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.password_reset.application.invalid_new_password_error import InvalidNewPasswordError
from app.password_reset.application.invalid_reset_token_error import InvalidResetTokenError

INVALID_REQUEST = "Requete invalide."


def _invalid_new_password(_: Request, error: Exception) -> JSONResponse:
    """Champ fautif et message fixe : la valeur saisie n'est jamais renvoyee."""
    invalid = cast(InvalidNewPasswordError, error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": INVALID_REQUEST,
            "fields": list(invalid.fields),
            "messages": list(invalid.messages),
        },
    )


def _invalid_reset_token(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour jeton inconnu, expire ou deja utilise."""
    invalid = cast(InvalidResetTokenError, error)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, content={"detail": invalid.message}
    )


def register_password_reset_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvalidNewPasswordError, _invalid_new_password)
    application.add_exception_handler(InvalidResetTokenError, _invalid_reset_token)
