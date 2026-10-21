import asyncio
from typing import Any

from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.http.overridable_send import Message, OverridableSend

LIVENESS_PATHS = frozenset({"/health"})


class ConcurrencyLimitMiddleware:
    """Borne le nombre de requêtes en cours dans l'instance ; l'excédent est rejeté (503).

    Pas de file d'attente : sous attaque, mieux vaut refuser vite que s'empiler. La liveness
    (`/health`) n'est jamais comptée ni refusée. Ce compteur borne une ressource de l'instance,
    il ne porte aucun état métier.
    """

    def __init__(
        self,
        app: Any,
        max_concurrent: int,
        events: BusinessEventLogger,
        exempt_paths: frozenset[str] = LIVENESS_PATHS,
    ) -> None:
        self._app = app
        self._slots = asyncio.Semaphore(max_concurrent)
        self._exempt_paths = exempt_paths
        self._events = events

    async def __call__(self, scope: Message, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"] in self._exempt_paths:
            await self._app(scope, receive, send)
            return
        if self._slots.locked():
            self._events.log(
                BusinessEvent.denied(
                    names.OVERLOADED, "concurrency_limit", attributes={"method": scope["method"]}
                )
            )
            gate = OverridableSend(send)
            gate.override(503, "Service unavailable", [(b"retry-after", b"1")])
            await gate.flush()
            return
        async with self._slots:
            await self._app(scope, receive, send)
