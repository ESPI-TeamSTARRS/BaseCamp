from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.application.verify_email import VerifyEmailUseCase
from app.registration.presentation.dependencies import (
    get_register_account_use_case,
    get_verify_email_use_case,
)
from app.registration.presentation.schemas.message_response import MessageResponse
from app.registration.presentation.schemas.register_request import RegisterRequest
from app.registration.presentation.schemas.verify_email_request import VerifyEmailRequest

router = APIRouter(tags=["registration"])

REGISTRATION_ACCEPTED = (
    "Demande prise en compte. Consultez votre boîte mail pour confirmer votre adresse."
)
EMAIL_VERIFIED = "Adresse email confirmée."


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse)
def register(
    body: RegisterRequest,
    use_case: Annotated[RegisterAccountUseCase, Depends(get_register_account_use_case)],
) -> MessageResponse:
    """Meme reponse que l'adresse soit libre ou deja inscrite (pas d'enumeration de comptes)."""
    use_case.execute(body.email, body.password.get_secret_value())
    return MessageResponse(message=REGISTRATION_ACCEPTED)


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    body: VerifyEmailRequest,
    use_case: Annotated[VerifyEmailUseCase, Depends(get_verify_email_use_case)],
) -> MessageResponse:
    use_case.execute(body.token)
    return MessageResponse(message=EMAIL_VERIFIED)
