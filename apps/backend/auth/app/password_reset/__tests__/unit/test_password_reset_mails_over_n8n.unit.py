import json

import httpx
import pytest

from app.password_reset.infrastructure.clients.email_password_reset_mailer import (
    EmailPasswordResetMailer,
)
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.n8n_email_sender import N8nEmailSender

TO = EmailAddress.of("camille@example.com")
SHARED = "valeur-de-test-du-secret-n8n"
BASE = "https://basecamp.example.test"


def _mailer(handler: httpx.MockTransport) -> EmailPasswordResetMailer:
    sender = N8nEmailSender(
        httpx.Client(transport=handler), "https://n8n.example.test/webhook/send-email", SHARED, 2.0
    )
    return EmailPasswordResetMailer(sender, BASE + "/")


def _recording() -> tuple[httpx.MockTransport, list[dict[str, str]]]:
    sent: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler), sent


class TestPasswordResetMailsOverN8n:
    def test_the_reset_link_is_a_clickable_html_link_with_the_token_in_the_fragment(self) -> None:
        transport, sent = _recording()

        _mailer(transport).send_reset_link(TO, "jeton-de-test")

        (mail,) = sent
        link = f"{BASE}/compte/reinitialiser#token=jeton-de-test"
        assert mail["to"] == "camille@example.com"
        assert f'<a href="{link}">{link}</a>' in mail["body"]
        assert "30 minutes" in mail["body"]

    def test_the_change_notification_has_no_link_and_is_plain_html_paragraphs(self) -> None:
        transport, sent = _recording()

        _mailer(transport).send_password_changed(TO)

        (mail,) = sent
        assert "<a " not in mail["body"] and mail["body"].startswith("<p>")
        assert "modifié" in mail["subject"]

    def test_a_refusal_is_a_delivery_error_without_the_token(self) -> None:
        mailer = _mailer(httpx.MockTransport(lambda request: httpx.Response(403, json={})))

        with pytest.raises(MailDeliveryError) as raised:
            mailer.send_reset_link(TO, "jeton-de-test")

        assert raised.value.cause == "http_403"
        assert "jeton-de-test" not in repr(raised.value.__dict__)
