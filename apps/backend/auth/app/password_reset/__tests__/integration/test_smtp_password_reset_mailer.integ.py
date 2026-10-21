import smtplib
from email.message import EmailMessage
from typing import Any, Self

import pytest

from app.password_reset.infrastructure.clients.smtp_password_reset_mailer import (
    SmtpPasswordResetMailer,
)
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.smtp_email_sender import SmtpEmailSender

TOKEN = "jeton-de-test-0123456789-abcdefghijklmnopqrstu"
TO = EmailAddress.of("camille@example.com")


class FakeSmtp:
    sent: list[EmailMessage] = []  # noqa: RUF012
    failure: Exception | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        if FakeSmtp.failure:
            raise FakeSmtp.failure

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.sent, FakeSmtp.failure = [], None
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)


def make_mailer() -> SmtpPasswordResetMailer:
    transport = SmtpEmailSender("mailpit", 1025, "comptes@basecamp.local", "", "", False, 5.0)
    return SmtpPasswordResetMailer(transport, "http://localhost:8080/")


class TestSmtpPasswordResetMailer:
    def test_the_link_carries_only_the_token_in_the_fragment(self) -> None:
        make_mailer().send_reset_link(TO, TOKEN)

        [message] = FakeSmtp.sent
        body = message.get_content()
        assert message["To"] == "camille@example.com"
        assert f"http://localhost:8080/compte/reinitialiser#token={TOKEN}" in body
        assert "?" not in body.split("http://localhost:8080")[1].split()[0]
        assert "camille" not in body
        assert "30 minutes" in body

    def test_the_change_notification_has_no_link_and_no_token(self) -> None:
        make_mailer().send_password_changed(TO)

        [message] = FakeSmtp.sent
        assert "modifié" in message["Subject"]
        assert "http" not in message.get_content()

    def test_transport_failures_become_a_delivery_error_without_detail(self) -> None:
        FakeSmtp.failure = OSError("refused")

        with pytest.raises(MailDeliveryError) as raised:
            make_mailer().send_reset_link(TO, TOKEN)

        assert TOKEN not in str(raised.value)
