from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status

from app.customer_identity.application.authenticate_customer import AuthenticateCustomerUseCase
from app.customer_identity.application.authorize_operator import AuthorizeOperatorUseCase
from app.customer_identity.application.customer_view import Customer
from app.customer_identity.application.forbidden_error import ForbiddenError
from app.customer_identity.application.identity_unavailable_error import IdentityUnavailableError
from app.customer_identity.application.operator_view import Operator
from app.customer_identity.application.unauthenticated_error import UnauthenticatedError

BEARER_SCHEME = "bearer"


def get_authenticate_customer_use_case(request: Request) -> AuthenticateCustomerUseCase:
    """Le cas d'usage est cable dans main.py (la presentation n'importe pas l'infrastructure)."""
    return cast(AuthenticateCustomerUseCase, request.app.state.authenticate_customer_use_case)


def bearer_token(request: Request) -> str | None:
    """Jeton du schema `Bearer`, ou `None` : un en-tete absent ou d'un autre schema n'est pas un jeton."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    token = credentials.strip()
    return token if scheme.lower() == BEARER_SCHEME and token else None


def current_customer(
    request: Request,
    use_case: Annotated[AuthenticateCustomerUseCase, Depends(get_authenticate_customer_use_case)],
) -> Customer:
    """Route reservee aux clients connectes : 401 generique, 503 si les cles sont illisibles."""
    try:
        return use_case.require(bearer_token(request))
    except UnauthenticatedError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=error.message,
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        ) from None
    except IdentityUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error.message,
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        ) from None


def optional_customer(
    request: Request,
    use_case: Annotated[AuthenticateCustomerUseCase, Depends(get_authenticate_customer_use_case)],
) -> Customer | None:
    """Route ouverte aux invites : `None` sans jeton, avec un jeton refuse ou sans cle lisible."""
    return use_case.optional(bearer_token(request))


def get_authorize_operator_use_case(request: Request) -> AuthorizeOperatorUseCase:
    return cast(AuthorizeOperatorUseCase, request.app.state.authorize_operator_use_case)


def current_operator(
    request: Request,
    use_case: Annotated[AuthorizeOperatorUseCase, Depends(get_authorize_operator_use_case)],
) -> Operator:
    """Routes d'administration : 401 sans jeton valide, 403 sans rôle `operator` ou second facteur, 503 sans clés."""
    try:
        return use_case.require(bearer_token(request))
    except UnauthenticatedError as error:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=error.message,
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        ) from None
    except ForbiddenError as error:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=error.message, headers={"Cache-Control": "no-store"}
        ) from None
    except IdentityUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error.message,
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        ) from None
