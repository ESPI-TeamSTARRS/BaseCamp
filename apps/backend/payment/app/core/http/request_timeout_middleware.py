import asyncio
from typing import Any

from app.core.events import service_event_names as names
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.http.concurrency_limit_middleware import LIVENESS_PATHS
from app.core.http.overridable_send import Message, OverridableSend


class _WriteTimeoutError(Exception):
    """Le client ne lit plus la réponse : la connexion est abandonnée."""


class RequestTimeoutMiddleware:
    """Délais de lecture du corps (408), d'envoi de la réponse et de durée totale (504).

    Un handler synchrone tourne dans un thread qu'on ne peut pas annuler : le délai libère le
    client et la connexion, `statement_timeout` borne ce que le thread fait en base.
    """

    def __init__(
        self,
        app: Any,
        read_timeout: float,
        write_timeout: float,
        request_timeout: float,
        events: BusinessEventLogger,
    ) -> None:
        self._app = app
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._request_timeout = request_timeout
        self._events = events

    async def __call__(self, scope: Message, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"] in LIVENESS_PATHS:
            await self._app(scope, receive, send)
            return
        gate = OverridableSend(send)

        async def bounded_receive() -> Message:
            try:
                message: Message = await asyncio.wait_for(receive(), self._read_timeout)
            except TimeoutError:
                self._refuse(gate, scope, 408, "read_timeout", [(b"connection", b"close")])
                return {"type": "http.disconnect"}
            return message

        async def bounded_send(message: Message) -> None:
            try:
                await asyncio.wait_for(gate(message), self._write_timeout)
            except TimeoutError:
                raise _WriteTimeoutError from None

        try:
            await asyncio.wait_for(
                self._app(scope, bounded_receive, bounded_send), self._request_timeout
            )
        except TimeoutError:
            self._refuse(gate, scope, 504, "request_timeout")
        except _WriteTimeoutError:
            return
        try:
            await asyncio.wait_for(gate.flush(), self._write_timeout)
        except TimeoutError:
            return

    def _refuse(
        self,
        gate: OverridableSend,
        scope: Message,
        status: int,
        reason: str,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        if gate.started or gate.overridden:
            return
        self._events.log(
            BusinessEvent.error(
                names.REQUEST_TIMEOUT, reason, attributes={"method": scope["method"]}
            )
        )
        gate.override(status, "Request timeout", headers)
