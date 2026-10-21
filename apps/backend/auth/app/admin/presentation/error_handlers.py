from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.admin.application.admin_errors import (
    AccountNotFoundError,
    AdminError,
    CannotDisableLastOperatorError,
    CannotDisableSelfError,
)

_STATUS = {
    AccountNotFoundError: status.HTTP_404_NOT_FOUND,
    CannotDisableSelfError: status.HTTP_409_CONFLICT,
    CannotDisableLastOperatorError: status.HTTP_409_CONFLICT,
}


def _admin_error(_: Request, error: Exception) -> JSONResponse:
    """Messages fixes : jamais de donnee saisie, seul le code stable permet de distinguer."""
    admin = cast(AdminError, error)
    return JSONResponse(
        status_code=_STATUS.get(type(admin), status.HTTP_400_BAD_REQUEST),
        content={"detail": admin.message, "code": admin.code},
        headers={"Cache-Control": "no-store"},
    )


def register_admin_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(AdminError, _admin_error)
