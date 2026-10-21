from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.service_token.domain.exceptions.invalid_client_credentials_error import (
    InvalidClientCredentialsError,
)
from app.service_token.domain.exceptions.rate_limit_exceeded_error import RateLimitExceededError


async def _invalid_client(_: Request, __: Exception) -> JSONResponse:
    """Meme statut, meme corps, memes en-tetes pour toutes les causes d'echec d'identification."""
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"error": "invalid_client"}
    )


async def _rate_limited(_: Request, error: Exception) -> JSONResponse:
    retry_after = cast(RateLimitExceededError, error).retry_after_seconds
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "rate_limited"},
        headers={"Retry-After": str(max(retry_after, 1))},
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(InvalidClientCredentialsError, _invalid_client)
    application.add_exception_handler(RateLimitExceededError, _rate_limited)
