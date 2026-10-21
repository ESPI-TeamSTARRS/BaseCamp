from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging.correlation import (
    CORRELATION_HEADER,
    is_valid_correlation_id,
    new_correlation_id,
    set_correlation_id,
)


class CorrelationIdMiddleware:
    """Reprend un X-Correlation-ID valide (sinon en genere un) et le renvoie dans la reponse."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get(CORRELATION_HEADER)
        correlation_id = incoming if is_valid_correlation_id(incoming) else new_correlation_id()
        assert correlation_id is not None  # noqa: S101 - rassure mypy, garanti ci-dessus
        set_correlation_id(correlation_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        await self._app(scope, receive, send_with_header)
