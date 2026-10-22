from typing import cast

from fastapi import HTTPException, Request, status

from app.core.client_address_resolver import ClientAddressResolver
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.application.login_account import LoginAccountUseCase
from app.login.application.logout_session import LogoutSessionUseCase
from app.login.application.refresh_session import RefreshSessionUseCase

BEARER_SCHEME = "bearer"
FORWARDED_HEADER = "x-forwarded-for"
CSRF_HEADER = "x-requested-with"


def get_login_account_use_case(request: Request) -> LoginAccountUseCase:
    """Les cas d'usage sont cables dans composition.py (la presentation n'importe pas l'infrastructure)."""
    return cast(LoginAccountUseCase, request.app.state.login_account_use_case)


def get_refresh_session_use_case(request: Request) -> RefreshSessionUseCase:
    return cast(RefreshSessionUseCase, request.app.state.refresh_session_use_case)


def get_logout_session_use_case(request: Request) -> LogoutSessionUseCase:
    return cast(LogoutSessionUseCase, request.app.state.logout_session_use_case)


def require_csrf_header(request: Request) -> None:
    """En-tete qu'une page d'un autre site ne peut pas poser sans pre-verification CORS refusee."""
    if not request.headers.get(CSRF_HEADER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requête refusée.")


def get_current_account_use_case(request: Request) -> GetCurrentAccountUseCase:
    return cast(GetCurrentAccountUseCase, request.app.state.get_current_account_use_case)


def get_public_keys_use_case(request: Request) -> GetPublicKeysUseCase:
    return cast(GetPublicKeysUseCase, request.app.state.get_public_keys_use_case)


def bearer_token(request: Request) -> str:
    """Jeton du schema `Bearer`, ou chaine vide : le cas d'usage le refuse comme tout jeton invalide."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    return credentials.strip() if scheme.lower() == BEARER_SCHEME else ""


def client_ip(request: Request) -> str | None:
    """Adresse reelle du client : le pair TCP, ou l'adresse relayee par un proxy de confiance.

    `X-Forwarded-For` n'est lu que si le pair est dans `APP_TRUSTED_PROXIES` (voir
    `ClientAddressResolver`); sinon un client pourrait choisir son adresse."""
    resolver = cast(ClientAddressResolver, request.app.state.client_address_resolver)
    peer = request.client.host if request.client else None
    return resolver.resolve(peer, request.headers.get(FORWARDED_HEADER))
