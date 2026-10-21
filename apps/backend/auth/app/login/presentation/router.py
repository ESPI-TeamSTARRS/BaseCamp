from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.login_account import LoginAccountUseCase
from app.login.presentation.dependencies import (
    bearer_token,
    client_ip,
    get_current_account_use_case,
    get_login_account_use_case,
)
from app.login.presentation.schemas.login_request import LoginRequest
from app.login.presentation.schemas.login_response import LoginResponse
from app.login.presentation.schemas.profile_response import ProfileResponse

router = APIRouter(tags=["login"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = (
    "/api/auth"  # le navigateur ne l'envoie qu'aux routes d'auth, via la passerelle
)
NO_STORE = "no-store"


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    use_case: Annotated[LoginAccountUseCase, Depends(get_login_account_use_case)],
) -> LoginResponse:
    """Meme 401 pour email inconnu, mauvais mot de passe et compte desactive."""
    result = use_case.execute(body.email, body.password.get_secret_value(), client_ip(request))
    response.set_cookie(
        REFRESH_COOKIE,
        result.refresh_token,
        max_age=result.refresh_expires_in,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = NO_STORE
    return LoginResponse(access_token=result.access_token, expires_in=result.expires_in)


@router.get("/me", response_model=ProfileResponse)
def me(
    request: Request,
    response: Response,
    use_case: Annotated[GetCurrentAccountUseCase, Depends(get_current_account_use_case)],
) -> ProfileResponse:
    profile = use_case.execute(bearer_token(request))
    response.headers["Cache-Control"] = NO_STORE
    return ProfileResponse(
        id=profile.id,
        email=profile.email,
        roles=list(profile.roles),
        email_verified=profile.email_verified,
    )
