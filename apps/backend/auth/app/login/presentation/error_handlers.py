from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.login.application.invalid_credentials_error import InvalidCredentialsError
from app.login.application.invalid_refresh_token_error import InvalidRefreshTokenError
from app.login.application.unauthenticated_error import UnauthenticatedError
from app.login.presentation.refresh_cookie import clear_refresh_cookie


def _invalid_credentials(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour email inconnu, mauvais mot de passe et compte desactive."""
    invalid = cast(InvalidCredentialsError, error)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": invalid.message},
        headers={"Cache-Control": "no-store"},
    )


def _unauthenticated(_: Request, error: Exception) -> JSONResponse:
    """Une seule reponse pour jeton absent, expire, falsifie ou revoque."""
    unauthenticated = cast(UnauthenticatedError, error)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": unauthenticated.message},
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


def _invalid_refresh_token(_: Request, error: Exception) -> JSONResponse:
    """401 unique; le cookie est efface pour que le front ne reessaie pas en boucle."""
    invalid = cast(InvalidRefreshTokenError, error)
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": invalid.message},
        headers={"Cache-Control": "no-store"},
    )
    clear_refresh_cookie(response)
    return response


def register_login_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvalidCredentialsError, _invalid_credentials)
    application.add_exception_handler(UnauthenticatedError, _unauthenticated)
    application.add_exception_handler(InvalidRefreshTokenError, _invalid_refresh_token)
