import ipaddress
from typing import cast

from fastapi import Request

from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.application.login_account import LoginAccountUseCase

BEARER_SCHEME = "bearer"
FORWARDED_HEADER = "x-forwarded-for"


def get_login_account_use_case(request: Request) -> LoginAccountUseCase:
    """Les cas d'usage sont cables dans composition.py (la presentation n'importe pas l'infrastructure)."""
    return cast(LoginAccountUseCase, request.app.state.login_account_use_case)


def get_current_account_use_case(request: Request) -> GetCurrentAccountUseCase:
    return cast(GetCurrentAccountUseCase, request.app.state.get_current_account_use_case)


def get_public_keys_use_case(request: Request) -> GetPublicKeysUseCase:
    return cast(GetPublicKeysUseCase, request.app.state.get_public_keys_use_case)


def bearer_token(request: Request) -> str:
    """Jeton du schema `Bearer`, ou chaine vide : le cas d'usage le refuse comme tout jeton invalide."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    return credentials.strip() if scheme.lower() == BEARER_SCHEME else ""


def client_ip(request: Request) -> str | None:
    """Adresse reelle posee par la passerelle (X-Forwarded-For), validee avant d'etre journalisee."""
    forwarded = request.headers.get(FORWARDED_HEADER, "").split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return request.client.host if request.client else None
