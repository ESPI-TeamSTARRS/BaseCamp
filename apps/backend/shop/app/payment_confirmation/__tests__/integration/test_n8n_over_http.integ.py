"""Adaptateur n8n contre un vrai serveur HTTP local : secret reçu, 403, délai dépassé, réponse valide."""

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import pytest

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.infrastructure.senders.n8n_confirmation_sender import (
    N8nConfirmationSender,
)

SHARED_VALUE = "valeur-de-test-du-secret-n8n"
MAIL = ConfirmationMail("camille.martin@example.org", "BC-ABCDEFGHJK", 4490, ())


class _FakeN8n:
    """Faux workflow : 403 sans le bon secret, réponse lente sur demande."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.delay = 0.0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"headers": dict(self.headers), "body": body})
                time.sleep(outer.delay)
                allowed = self.headers.get("X-Mail-Secret") == SHARED_VALUE
                payload = json.dumps({"ok": True} if allowed else {"message": "Forbidden"}).encode()
                self.send_response(200 if allowed else 403)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                return None

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/webhook/send-email"


@pytest.fixture
def n8n() -> Iterator[_FakeN8n]:
    fake = _FakeN8n()
    fake.thread.start()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def _sender(
    n8n: _FakeN8n, secret: str = SHARED_VALUE, timeout: float = 2.0
) -> N8nConfirmationSender:
    return N8nConfirmationSender(httpx.Client(), n8n.url, secret, timeout_seconds=timeout)


class TestOverRealHttp:
    def test_a_mail_reaches_the_workflow_with_the_secret_and_a_json_body(
        self, n8n: _FakeN8n
    ) -> None:
        _sender(n8n).send(MAIL)

        (received,) = n8n.requests
        assert received["headers"]["X-Mail-Secret"] == SHARED_VALUE
        assert set(received["body"]) == {"to", "subject", "body"}

    def test_a_wrong_secret_is_refused_with_403_and_reported(self, n8n: _FakeN8n) -> None:
        with pytest.raises(ConfirmationDeliveryError) as error:
            _sender(n8n, secret="mauvais-secret").send(MAIL)  # noqa: S106

        assert error.value.reason == "http_403"

    def test_a_slow_workflow_is_cut_at_the_timeout(self, n8n: _FakeN8n) -> None:
        n8n.delay = 1.5
        started = time.monotonic()

        with pytest.raises(ConfirmationDeliveryError) as error:
            _sender(n8n, timeout=0.3).send(MAIL)

        assert error.value.reason == "timeout"
        assert time.monotonic() - started < 1.2
