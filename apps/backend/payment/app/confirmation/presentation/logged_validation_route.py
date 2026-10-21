from collections.abc import Callable, Coroutine
from typing import Any, cast

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.confirmation.application.confirmation_services import ConfirmationServices


class LoggedValidationRoute(APIRoute):
    """Journalise (sans la valeur reçue) les demandes de confirmation refusées à la validation."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def logged(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                services = cast(ConfirmationServices, request.app.state.confirmation_services)
                services.record_rejection.execute(
                    raw_intent_id=str(request.path_params.get("intent_id", "")),
                    invalid_method=any(
                        item["loc"][-1:] == ("payment_method",) for item in error.errors()
                    ),
                )
                raise

        return logged
