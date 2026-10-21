from typing import cast

from fastapi import Request

from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.password_reset.application.reset_password import ResetPasswordUseCase


def get_request_password_reset_use_case(request: Request) -> RequestPasswordResetUseCase:
    """Le cas d'usage est cable dans composition.py (la presentation n'importe pas l'infrastructure)."""
    return cast(RequestPasswordResetUseCase, request.app.state.request_password_reset_use_case)


def get_reset_password_use_case(request: Request) -> ResetPasswordUseCase:
    return cast(ResetPasswordUseCase, request.app.state.reset_password_use_case)
