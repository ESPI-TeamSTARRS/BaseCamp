from ipaddress import ip_address
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status

from app.caller_identity.application.caller_errors import (
    CallerForbiddenError,
    CallerUnauthorizedError,
    IdentityUnavailableError,
)
from app.caller_identity.application.caller_view import Caller, CallerRequirement
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


PAYMENTS_WRITE = "payments:write"
REFUNDS_WRITE = "refunds:write"
OPERATOR_ROLE = "operator"

# Routes de paiement : jeton de SERVICE portant `payments:write` (jamais un jeton client).
SERVICE_REQUIREMENT = CallerRequirement(scope=PAYMENTS_WRITE)
# Remboursement : jeton de service portant `refunds:write` OU jeton client d'un OPERATEUR.
REFUND_REQUIREMENT = CallerRequirement(scope=REFUNDS_WRITE, operator_role=OPERATOR_ROLE)


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.startswith(_BEARER_PREFIX):
        return authorization[len(_BEARER_PREFIX) :]
    return None


def authenticate_caller(
    request: Request,
    services: IntentServices,
    authorization: str | None,
    requirement: CallerRequirement,
) -> Caller:
    """Identifie l'appelant : un seul 401 pour tout jeton refuse, 403 si authentique mais insuffisant."""
    try:
        caller = services.authenticate.execute(
            _bearer(authorization), requirement, _client_ip(request)
        )
    except CallerUnauthorizedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except CallerForbiddenError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from None
    except IdentityUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
            headers={"Retry-After": "5"},
        ) from None
    # Nom de l'appelant pour la ligne de journal de requete (jamais le jeton).
    request.state.caller = caller.subject
    return caller


def get_calling_service(
    request: Request,
    services: Annotated[IntentServices, Depends(get_intent_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Appelant d'une route de paiement : le client de service (`sub` du jeton), ex. `shop`."""
    return authenticate_caller(request, services, authorization, SERVICE_REQUIREMENT).subject


def get_refund_caller(
    request: Request,
    services: Annotated[IntentServices, Depends(get_intent_services)],
    authorization: Annotated[str | None, Header()] = None,
) -> Caller:
    """Appelant d'un remboursement : service `refunds:write` ou operateur (identite consignee)."""
    return authenticate_caller(request, services, authorization, REFUND_REQUIREMENT)
