from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

EXTRA_FORBIDDEN = "extra_forbidden"


def _invalid_request(_: Request, error: Exception) -> JSONResponse:
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
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Requete invalide.", "fields": fields},
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(RequestValidationError, _invalid_request)
