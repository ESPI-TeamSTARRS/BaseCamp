from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.login_account import LoginAccountUseCase
from app.login.application.logout_session import LogoutSessionUseCase
from app.login.application.refresh_session import RefreshSessionUseCase
from app.login.presentation.dependencies import (
    bearer_token,
    client_ip,
    get_current_account_use_case,
    get_login_account_use_case,
    get_logout_session_use_case,
    get_refresh_session_use_case,
    require_csrf_header,
)
from app.login.presentation.refresh_cookie import (
    REFRESH_COOKIE,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.login.presentation.schemas.login_request import LoginRequest
from app.login.presentation.schemas.login_response import LoginResponse
from app.login.presentation.schemas.profile_response import ProfileResponse

router = APIRouter(tags=["login"])

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
    set_refresh_cookie(response, result.refresh_token, result.refresh_expires_in)
    response.headers["Cache-Control"] = NO_STORE
    return LoginResponse(access_token=result.access_token, expires_in=result.expires_in)


@router.post("/refresh", response_model=LoginResponse, dependencies=[Depends(require_csrf_header)])
def refresh(
    request: Request,
    response: Response,
    use_case: Annotated[RefreshSessionUseCase, Depends(get_refresh_session_use_case)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> LoginResponse:
    """Rotation : nouveau jeton d'acces et nouveau cookie; le precedent ne sert plus."""
    result = use_case.execute(refresh_token or "", client_ip(request))
    set_refresh_cookie(response, result.refresh_token, result.refresh_expires_in)
    response.headers["Cache-Control"] = NO_STORE
    return LoginResponse(access_token=result.access_token, expires_in=result.expires_in)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def logout(
    request: Request,
    response: Response,
    use_case: Annotated[LogoutSessionUseCase, Depends(get_logout_session_use_case)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> None:
    """Idempotent : 204 que le jeton soit valide, inconnu ou absent; le cookie est efface."""
    use_case.execute(refresh_token, client_ip(request))
    clear_refresh_cookie(response)
    response.headers["Cache-Control"] = NO_STORE


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
