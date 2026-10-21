from collections.abc import Callable
from typing import cast

from fastapi import Request

from app.login.application.authorize_request import AuthorizeRequestUseCase
from app.login.application.principal import Principal
from app.login.presentation.dependencies import bearer_token


def require_role(*roles: str) -> Callable[[Request], Principal]:
    """Dependance FastAPI reutilisable : `Depends(require_role("operator"))`.

    Sans jeton valide : 401 generique; avec un jeton valide mais sans l'un des roles : 403
    generique. Les roles sont ceux du jeton signe; la route recoit le `Principal` (id et roles).
    Reutilisable par n'importe quel endpoint d'administration ou de back-office, avec un ou
    plusieurs roles acceptes.
    """
    required = frozenset(roles)
    if not required:
        raise ValueError("require_role needs at least one role")

    def dependency(request: Request) -> Principal:
        use_case = cast(AuthorizeRequestUseCase, request.app.state.authorize_request_use_case)
        return use_case.execute(bearer_token(request), required)

    return dependency
