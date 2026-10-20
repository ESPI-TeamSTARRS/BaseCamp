from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _invalid_request(_: Request, error: Exception) -> JSONResponse:
    """422 assaini : on nomme les parametres fautifs, jamais leur valeur."""
    errors = cast(RequestValidationError, error).errors()
    fields = sorted({str(item["loc"][-1]) for item in errors if item["loc"]})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Requete invalide.", "fields": fields},
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(RequestValidationError, _invalid_request)
