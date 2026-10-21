from typing import cast

from fastapi import Request

from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.application.verify_email import VerifyEmailUseCase


def get_register_account_use_case(request: Request) -> RegisterAccountUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(RegisterAccountUseCase, request.app.state.register_account_use_case)


def get_verify_email_use_case(request: Request) -> VerifyEmailUseCase:
    return cast(VerifyEmailUseCase, request.app.state.verify_email_use_case)
