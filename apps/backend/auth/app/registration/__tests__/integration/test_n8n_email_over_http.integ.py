"""Le transport n8n de bout en bout contre un VRAI serveur HTTP local (faux workflow), jamais le vrai n8n.

Prouve : corps JSON et en-tete secret recus, 403 sans le bon secret, delai depasse, et surtout qu'un
echec n'annule jamais l'action (reponse inchangee, evenement journalise, aucune donnee sensible).
"""

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app
from app.registration.__tests__.fakes import FakeClock, FakeEmailFingerprinter, FakePasswordHasher
from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.email_registration_mailer import (
    EmailRegistrationMailer,
)
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.n8n_email_sender import N8nEmailSender
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

SHARED = "valeur-de-test-du-secret-n8n"
VALID = {"email": "camille@example.com", "password": "sentier-du-mont-blanc"}
BASE = "https://basecamp.example.test"


class FakeN8n:
    """Faux workflow : 403 sans le bon secret, reponse lente sur demande."""

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
                allowed = self.headers.get("X-Mail-Secret") == SHARED
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
def n8n() -> Iterator[FakeN8n]:
    fake = FakeN8n()
    fake.thread.start()
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


def _sender(n8n: FakeN8n, secret: str = SHARED, timeout: float = 2.0) -> N8nEmailSender:
    return N8nEmailSender(httpx.Client(), n8n.url, secret, timeout_seconds=timeout)


class TestOverRealHttp:
    def test_a_mail_reaches_the_workflow_with_the_secret_and_a_json_body(
        self, n8n: FakeN8n
    ) -> None:
        _sender(n8n).send(
            EmailAddress.of("camille@example.com"), "Sujet", "Bonjour\n\nhttps://a.example/x"
        )

        (received,) = n8n.requests
        assert received["headers"]["X-Mail-Secret"] == SHARED
        assert set(received["body"]) == {"to", "subject", "body"}
        assert received["body"]["to"] == "camille@example.com"
        assert '<a href="https://a.example/x">' in received["body"]["body"]

    def test_without_the_right_secret_the_workflow_answers_403(self, n8n: FakeN8n) -> None:
        with pytest.raises(MailDeliveryError) as raised:
            _sender(n8n, secret="mauvais").send(EmailAddress.of("camille@example.com"), "S", "B")

        assert raised.value.cause == "http_403"

    def test_a_slow_workflow_times_out(self, n8n: FakeN8n) -> None:
        n8n.delay = 1.0

        with pytest.raises(MailDeliveryError) as raised:
            _sender(n8n, timeout=0.2).send(EmailAddress.of("camille@example.com"), "S", "B")

        assert raised.value.cause == "timeout"


class Stack:
    """Application reelle (routes, SQL en memoire) dont les mails passent par le transport n8n."""

    def __init__(self, n8n: FakeN8n, secret: str) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        AuthBase.metadata.create_all(self.engine)
        self.events = InMemoryBusinessEventLogger()
        self.application = create_app()
        self.application.state.register_account_use_case = RegisterAccountUseCase(
            lambda: SqlAlchemyUnitOfWork(self.engine),
            PasswordPolicy(FileCommonPasswordList()),
            FakePasswordHasher(),
            SecureTokenGenerator(),
            EmailRegistrationMailer(
                N8nEmailSender(httpx.Client(), n8n.url, secret, timeout_seconds=2.0), BASE
            ),
            FakeClock(),
            self.events,
            FakeEmailFingerprinter(),
        )

    def users(self) -> int:
        with self.engine.connect() as connection:
            return int(connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one())


class TestRegistrationOverN8n:
    def test_the_verification_link_is_sent_as_html_through_the_workflow(self, n8n: FakeN8n) -> None:
        stack = Stack(n8n, SHARED)

        with TestClient(stack.application) as client:
            response = client.post("/register", json=VALID)

        assert response.status_code == 202
        (received,) = n8n.requests
        body = received["body"]["body"]
        assert received["body"]["to"] == "camille@example.com"
        assert f'<a href="{BASE}/compte/verification#token=' in body
        assert "<p>" in body

    def test_a_refused_secret_never_cancels_the_registration(self, n8n: FakeN8n) -> None:
        stack = Stack(n8n, "mauvais-secret")

        with TestClient(stack.application) as client:
            ok = client.post("/register", json=VALID)
            same_shape = Stack(n8n, SHARED)
            with TestClient(same_shape.application) as healthy:
                reference = healthy.post("/register", json=VALID)

        assert (ok.status_code, ok.json()) == (reference.status_code, reference.json())
        assert stack.users() == 1  # l'inscription est faite malgre le 403 de n8n
        [failure] = [e for e in stack.events.events if e.event == "auth.email_delivery_failed"]
        assert failure.reason == "mail_delivery_failed"
        assert dict(failure.attributes) == {"kind": "verification", "cause": "http_403"}

    def test_a_timeout_never_delays_nor_cancels_the_registration(self, n8n: FakeN8n) -> None:
        n8n.delay = 1.0
        stack = Stack(n8n, SHARED)
        stack.application.state.register_account_use_case._mailer._transport._timeout = 0.2

        with TestClient(stack.application) as client:
            response = client.post("/register", json=VALID)

        assert response.status_code == 202 and stack.users() == 1
        failures = [e for e in stack.events.events if e.event == "auth.email_delivery_failed"]
        assert [dict(f.attributes)["cause"] for f in failures] == ["timeout"]

    def test_no_address_link_or_secret_reaches_the_events(self, n8n: FakeN8n) -> None:
        stack = Stack(n8n, "mauvais-secret")

        with TestClient(stack.application) as client:
            client.post("/register", json=VALID)

        text_of_events = repr(stack.events.events)
        for forbidden in ("camille@example.com", "token=", "mauvais-secret", SHARED, "flux"):
            assert forbidden not in text_of_events
