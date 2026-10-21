from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.refund.application.refund_services import RefundServices


class LoggedValidationRoute(APIRoute):
    """Journalise (sans la valeur reçue) les remboursements refusés à la validation."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def logged(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                services = cast(RefundServices, request.app.state.refund_services)
                services.record_rejection.execute(str(request.path_params.get("intent_id", "")))
                raise

        return logged
