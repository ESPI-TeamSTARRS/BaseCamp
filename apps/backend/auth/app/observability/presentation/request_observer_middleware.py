import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.application.record_request import RecordRequestUseCase

CALLER_STATE_KEY = "caller"


class RequestObserverMiddleware:
    """Mesure chaque requête HTTP et la signale (compteurs et ligne de journal) une fois terminée.

    La route est le gabarit trouvé par le routeur (`scope["route"]`), l'appelant est posé dans
    `scope["state"]` par l'authentification. Une exception non gérée est comptée en 500 puis
    relancée au gestionnaire d'erreurs qui répond.
    """

    def __init__(self, app: ASGIApp, record: RecordRequestUseCase) -> None:
        self._app = app
        self._record = record

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_and_remember(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, send_and_remember)
        finally:
            route: Any = scope.get("route")
            caller = scope.get("state", {}).get(CALLER_STATE_KEY)
            self._record.execute(
                getattr(route, "path", None),
                scope["method"],
                status,
                time.perf_counter() - started,
                caller if isinstance(caller, str) else None,
            )
