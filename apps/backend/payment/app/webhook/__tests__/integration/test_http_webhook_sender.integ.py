"""Envoi HTTP réel contre un récepteur factice local (aucun accès au réseau extérieur)."""

import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import pytest

from app.webhook.infrastructure.senders.http_webhook_sender import HttpWebhookSender

BODY = '{"id":"evt","type":"payment.succeeded"}'
SIGNATURE = "t=1790000000,v1=" + "ab" * 32


class Receiver:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], bytes]] = []
        self.respond: Callable[[BaseHTTPRequestHandler], None] = lambda h: h.send_response(200)
        self.url = ""


@pytest.fixture
def receiver() -> Iterator[Receiver]:
    state = Receiver()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            headers = {key.lower(): value for key, value in self.headers.items()}
            state.requests.append((self.path, headers, self.rfile.read(length)))
            state.respond(self)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_port}/webhooks/payment"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


class TestSend:
    def test_a_2xx_answer_is_a_delivery_and_the_request_carries_the_published_headers(
        self, receiver: Receiver
    ) -> None:
        event_id = uuid4()

        result = HttpWebhookSender(receiver.url, 2.0).send(event_id, BODY, SIGNATURE)

        assert (result.delivered, result.status_code, result.reason) == (True, 200, None)
        path, headers, body = receiver.requests[0]
        assert path == "/webhooks/payment"
        assert body == BODY.encode()
        assert headers["x-payment-signature"] == SIGNATURE
        assert headers["x-payment-event-id"] == str(event_id)
        assert headers["content-type"] == "application/json"

    def test_any_2xx_is_accepted(self, receiver: Receiver) -> None:
        receiver.respond = lambda h: h.send_response(204)

        assert HttpWebhookSender(receiver.url, 2.0).send(uuid4(), BODY, SIGNATURE).delivered

    @pytest.mark.parametrize("status", [400, 404, 409, 500, 503])
    def test_a_non_2xx_answer_is_a_failure_with_its_status_code(
        self, receiver: Receiver, status: int
    ) -> None:
        receiver.respond = lambda h: h.send_response(status)

        result = HttpWebhookSender(receiver.url, 2.0).send(uuid4(), BODY, SIGNATURE)

        assert (result.delivered, result.reason, result.status_code) == (
            False,
            f"http_{status}",
            status,
        )

    def test_a_redirect_is_not_followed_so_the_signature_never_leaves_the_target(
        self, receiver: Receiver
    ) -> None:
        def redirect(handler: BaseHTTPRequestHandler) -> None:
            handler.send_response(302)
            handler.send_header("Location", "http://127.0.0.1:9/elsewhere")

        receiver.respond = redirect

        result = HttpWebhookSender(receiver.url, 2.0).send(uuid4(), BODY, SIGNATURE)

        assert (result.delivered, result.reason) == (False, "http_302")
        assert len(receiver.requests) == 1

    def test_a_refused_connection_is_a_failure_not_an_exception(self, receiver: Receiver) -> None:
        result = HttpWebhookSender("http://127.0.0.1:9/hook", 1.0).send(uuid4(), BODY, SIGNATURE)

        assert (result.delivered, result.reason, result.status_code) == (
            False,
            "connection_error",
            None,
        )

    def test_a_silent_receiver_ends_in_a_timeout(self, receiver: Receiver) -> None:
        receiver.respond = lambda h: time.sleep(0.6) or h.send_response(200)

        result = HttpWebhookSender(receiver.url, 0.2).send(uuid4(), BODY, SIGNATURE)

        assert (result.delivered, result.reason) == (False, "timeout")

    def test_an_unknown_host_is_a_connection_failure(self) -> None:
        result = HttpWebhookSender("http://nope.invalid/hook", 1.0).send(uuid4(), BODY, SIGNATURE)

        assert (result.delivered, result.reason) == (False, "connection_error")

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://shop/hook", "shop/hook", ""])
    def test_only_http_urls_are_ever_called(self, url: str) -> None:
        with pytest.raises(ValueError, match="http"):
            HttpWebhookSender(url, 1.0)

    def test_the_url_is_never_part_of_the_failure_reason(self) -> None:
        url = "http://user:hunter2@127.0.0.1:9/hook"

        result = HttpWebhookSender(url, 1.0).send(uuid4(), BODY, SIGNATURE)

        assert "hunter2" not in repr(result)
        assert "hunter2" not in repr(HttpWebhookSender(url, 1.0))
