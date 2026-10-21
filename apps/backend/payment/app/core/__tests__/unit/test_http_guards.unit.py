"""Garde-fous HTTP : taille du corps, délais, requêtes simultanées (ASGI pur, sans réseau)."""

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events import service_event_names as names
from app.core.http.body_size_limit_middleware import BodySizeLimitMiddleware
from app.core.http.concurrency_limit_middleware import ConcurrencyLimitMiddleware
from app.core.http.request_timeout_middleware import RequestTimeoutMiddleware

Message = dict[str, Any]
EVENTS = InMemoryBusinessEventLogger()
Receive = Callable[[], Awaitable[Message]]


def _scope(
    path: str = "/payments/intents", headers: list[tuple[bytes, bytes]] | None = None
) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": headers or [],
    }


async def _echo_app(scope: Any, receive: Receive, send: Any) -> None:
    """Application témoin : lit tout le corps puis répond 200."""
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _receive_of(*chunks: bytes) -> Receive:
    queue: list[Message] = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> Message:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    return receive


async def _run(app: Any, scope: dict[str, Any], receive: Receive) -> list[Message]:
    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def _start(sent: list[Message]) -> Message:
    return next(m for m in sent if m["type"] == "http.response.start")


def _status(sent: list[Message]) -> int:
    return int(_start(sent)["status"])


def _body(sent: list[Message]) -> dict[str, Any]:
    raw = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return json.loads(raw)  # type: ignore[no-any-return]


class TestBodySizeLimit:
    async def test_declared_length_above_the_limit_gets_413_without_reading(self) -> None:
        app = BodySizeLimitMiddleware(_echo_app, max_bytes=10, events=EVENTS)

        sent = await _run(app, _scope(headers=[(b"content-length", b"11")]), _receive_of(b"x"))

        assert _status(sent) == 413
        assert _body(sent) == {"detail": "Payload too large"}

    async def test_streamed_body_above_the_limit_gets_413(self) -> None:
        app = BodySizeLimitMiddleware(_echo_app, max_bytes=10, events=EVENTS)

        sent = await _run(app, _scope(), _receive_of(b"123456", b"7890123"))

        assert _status(sent) == 413

    async def test_body_within_the_limit_passes(self) -> None:
        app = BodySizeLimitMiddleware(_echo_app, max_bytes=10, events=EVENTS)
        scope = _scope(headers=[(b"content-length", b"10")])

        sent = await _run(app, scope, _receive_of(b"0123456789"))

        assert _status(sent) == 200

    async def test_application_error_response_is_replaced_by_the_413(self) -> None:
        async def reacting(scope: Any, receive: Receive, send: Any) -> None:
            await receive()  # dépasse la limite : l'application croit à une déconnexion
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"bad"})

        app = BodySizeLimitMiddleware(reacting, max_bytes=3, events=EVENTS)

        sent = await _run(app, _scope(), _receive_of(b"123456"))

        assert _status(sent) == 413
        assert b"bad" not in b"".join(m.get("body", b"") for m in sent)

    async def test_non_http_scopes_pass_through(self) -> None:
        calls: list[str] = []

        async def inner(scope: Any, receive: Any, send: Any) -> None:
            calls.append(scope["type"])

        await BodySizeLimitMiddleware(inner, max_bytes=1, events=EVENTS)(
            {"type": "lifespan"}, None, None
        )

        assert calls == ["lifespan"]


class TestRequestTimeout:
    def _app(self, inner: Any) -> RequestTimeoutMiddleware:
        return RequestTimeoutMiddleware(
            inner, read_timeout=0.05, write_timeout=0.05, request_timeout=0.2, events=EVENTS
        )

    async def test_slow_body_upload_gets_408(self) -> None:
        async def never() -> Message:
            await asyncio.sleep(5)
            return {"type": "http.disconnect"}

        sent = await _run(self._app(_echo_app), _scope(), never)

        assert _status(sent) == 408

    async def test_slow_handler_gets_504(self) -> None:
        async def slow(scope: Any, receive: Receive, send: Any) -> None:
            await asyncio.sleep(5)

        sent = await _run(self._app(slow), _scope(), _receive_of(b"{}"))

        assert _status(sent) == 504
        assert _body(sent) == {"detail": "Request timeout"}

    async def test_fast_request_is_untouched(self) -> None:
        sent = await _run(self._app(_echo_app), _scope(), _receive_of(b"{}"))

        assert _status(sent) == 200

    async def test_stalled_client_write_is_abandoned(self) -> None:
        async def stalled(_: Message) -> None:
            await asyncio.sleep(5)

        await self._app(_echo_app)(_scope(), _receive_of(b"{}"), stalled)  # ne bloque pas


class TestConcurrencyLimit:
    async def test_excess_requests_are_shed_with_503_and_retry_after(self) -> None:
        release = asyncio.Event()

        async def blocked(scope: Any, receive: Receive, send: Any) -> None:
            await release.wait()
            await _echo_app(scope, receive, send)

        app = ConcurrencyLimitMiddleware(blocked, max_concurrent=2, events=EVENTS)
        tasks = [asyncio.create_task(_run(app, _scope(), _receive_of(b""))) for _ in range(2)]
        await asyncio.sleep(0.05)

        shed = await _run(app, _scope(), _receive_of(b""))
        release.set()
        served = await asyncio.gather(*tasks)

        assert _status(shed) == 503
        assert (b"retry-after", b"1") in _start(shed)["headers"]
        assert [_status(s) for s in served] == [200, 200]

    async def test_liveness_is_never_shed(self) -> None:
        release = asyncio.Event()

        async def blocked(scope: Any, receive: Receive, send: Any) -> None:
            await release.wait()
            await _echo_app(scope, receive, send)

        app = ConcurrencyLimitMiddleware(blocked, max_concurrent=1, events=EVENTS)
        busy = asyncio.create_task(_run(app, _scope(), _receive_of(b"")))
        await asyncio.sleep(0.05)
        release.set()

        health = await _run(app, _scope("/health"), _receive_of(b""))
        await busy

        assert _status(health) == 200

    async def test_slot_is_released_when_the_request_fails(self) -> None:
        calls = 0

        async def flaky(scope: Any, receive: Receive, send: Any) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            await _echo_app(scope, receive, send)

        app = ConcurrencyLimitMiddleware(flaky, max_concurrent=1, events=EVENTS)
        with contextlib.suppress(RuntimeError):
            await _run(app, _scope(), _receive_of(b""))

        sent = await _run(app, _scope(), _receive_of(b""))

        assert _status(sent) == 200

    async def test_non_http_scopes_pass_through(self) -> None:
        calls: list[str] = []

        async def inner(scope: Any, receive: Any, send: Any) -> None:
            calls.append(scope["type"])

        await ConcurrencyLimitMiddleware(inner, max_concurrent=1, events=EVENTS)(
            {"type": "websocket"}, None, None
        )

        assert calls == ["websocket"]


class TestGuardEvents:
    async def test_each_refusal_emits_one_business_event_without_the_request_content(self) -> None:
        events = InMemoryBusinessEventLogger()
        body_app = BodySizeLimitMiddleware(_echo_app, max_bytes=3, events=events)
        timeout_app = RequestTimeoutMiddleware(
            _echo_app, read_timeout=0.05, write_timeout=0.05, request_timeout=0.2, events=events
        )

        async def never() -> Message:
            await asyncio.sleep(5)
            return {"type": "http.disconnect"}

        await _run(body_app, _scope(), _receive_of(b"secret-body-4242"))
        await _run(timeout_app, _scope(), never)
        release = asyncio.Event()

        async def blocked(scope: Any, receive: Receive, send: Any) -> None:
            await release.wait()

        shed_app = ConcurrencyLimitMiddleware(blocked, max_concurrent=1, events=events)
        busy = asyncio.create_task(_run(shed_app, _scope(), _receive_of(b"")))
        await asyncio.sleep(0.05)
        await _run(shed_app, _scope(), _receive_of(b""))
        release.set()
        await busy

        assert [(e.event, e.outcome.value, e.reason) for e in events.events] == [
            (names.PAYLOAD_TOO_LARGE, "denied", "payload_too_large"),
            (names.REQUEST_TIMEOUT, "error", "read_timeout"),
            (names.OVERLOADED, "denied", "concurrency_limit"),
        ]
        assert "secret-body" not in str(events.events)
