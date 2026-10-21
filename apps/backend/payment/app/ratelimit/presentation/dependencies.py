from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request

from app.ratelimit.application.check_rate_limit import CheckRateLimitUseCase


def rate_limited(route: str, caller_dependency: Callable[..., str]) -> Callable[..., None]:
    """Dépendance de route : décompte une requête pour (appelant authentifié, route).

    L'appelant vient de `caller_dependency` : une requête non authentifiée est refusée (401)
    avant tout décompte et ne consomme donc le budget de personne.
    """

    def check(request: Request, caller: Annotated[str, Depends(caller_dependency)]) -> None:
        use_case = cast(CheckRateLimitUseCase, request.app.state.rate_limiter)
        use_case.execute(caller, route)

    return check
