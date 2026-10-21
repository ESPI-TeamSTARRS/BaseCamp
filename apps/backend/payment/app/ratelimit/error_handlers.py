from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging.correlation import CORRELATION_HEADER, current_correlation_id
from app.ratelimit.application.exceptions.rate_limit_exceeded_error import RateLimitExceededError


async def _too_many_requests(_: Request, error: Exception) -> JSONResponse:
    retry_after = error.retry_after_seconds if isinstance(error, RateLimitExceededError) else 1
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests"},
        headers={"Retry-After": str(retry_after), CORRELATION_HEADER: current_correlation_id()},
    )


def register_rate_limit_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(RateLimitExceededError, _too_many_requests)
