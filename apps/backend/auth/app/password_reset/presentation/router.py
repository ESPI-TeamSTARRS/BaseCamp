from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.password_reset.application.reset_password import ResetPasswordUseCase
from app.password_reset.presentation.dependencies import (
    get_request_password_reset_use_case,
    get_reset_password_use_case,
)
from app.password_reset.presentation.schemas.forgot_password_request import ForgotPasswordRequest
from app.password_reset.presentation.schemas.message_response import PasswordResetMessageResponse
from app.password_reset.presentation.schemas.reset_password_request import ResetPasswordRequest

router = APIRouter(prefix="/password", tags=["password-reset"])

RESET_REQUESTED = (
    "Si un compte existe pour cette adresse, un email de réinitialisation vient d'être envoyé."
)
PASSWORD_CHANGED = "Mot de passe modifié. Vous pouvez vous reconnecter."  # noqa: S105


@router.post(
    "/forgot", status_code=status.HTTP_202_ACCEPTED, response_model=PasswordResetMessageResponse
)
def forgot_password(
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    use_case: Annotated[RequestPasswordResetUseCase, Depends(get_request_password_reset_use_case)],
) -> PasswordResetMessageResponse:
    """Toujours la meme reponse; l'email part apres elle (ni existence du compte, ni panne SMTP visibles)."""
    pending = use_case.execute(body.email)
    if pending is not None:
        background.add_task(use_case.deliver, pending)
    return PasswordResetMessageResponse(message=RESET_REQUESTED)


@router.post("/reset", response_model=PasswordResetMessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    use_case: Annotated[ResetPasswordUseCase, Depends(get_reset_password_use_case)],
) -> PasswordResetMessageResponse:
    use_case.execute(body.token.get_secret_value(), body.password.get_secret_value())
    return PasswordResetMessageResponse(message=PASSWORD_CHANGED)
