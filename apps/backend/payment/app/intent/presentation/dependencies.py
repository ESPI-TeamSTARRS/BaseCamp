from ipaddress import ip_address
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from app.intent.application.exceptions.unauthorized_service_error import UnauthorizedServiceError
from app.intent.application.intent_services import IntentServices

_BEARER_PREFIX = "Bearer "
_FORWARDED_FOR = "x-forwarded-for"


def _client_ip(request: Request) -> str | None:
    """Adresse du client posee par la passerelle (premier maillon de X-Forwarded-For), si valide."""
    forwarded = request.headers.get(_FORWARDED_FOR, "")
    candidate = forwarded.split(",")[0].strip() or (request.client.host if request.client else "")
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


def get_intent_services(request: Request) -> IntentServices:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(IntentServices, request.app.state.intent_services)


def get_calling_service(
    request: Request,
    services: Annotated[IntentServices, Depends(get_intent_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Retourne l'appelant authentifié ; la même réponse 401 sert à tous les échecs."""
    token = (
        authorization[len(_BEARER_PREFIX) :]
        if authorization and authorization.startswith(_BEARER_PREFIX)
        else None
    )
    try:
        return services.authenticate.execute(token, _client_ip(request))
    except UnauthorizedServiceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
