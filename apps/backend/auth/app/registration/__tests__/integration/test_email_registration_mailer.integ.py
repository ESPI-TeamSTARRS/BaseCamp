import smtplib
from email.message import EmailMessage
from typing import Any, Self

import pytest

from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.clients.email_registration_mailer import (
    EmailRegistrationMailer,
)
from app.registration.infrastructure.clients.smtp_email_sender import SmtpEmailSender

TOKEN = "jeton-factice"


class FakeSmtp:
    sent: list[EmailMessage] = []  # noqa: RUF012
    events: list[str] = []  # noqa: RUF012
    failure: Exception | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        FakeSmtp.events.append(f"connect:{host}:{port}:{timeout}")
        if FakeSmtp.failure:
            raise FakeSmtp.failure

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def starttls(self) -> None:
        FakeSmtp.events.append("starttls")

    def login(self, user: str, secret: str) -> None:
        FakeSmtp.events.append(f"login:{user}")

    def send_message(self, message: EmailMessage) -> None:
        FakeSmtp.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.sent, FakeSmtp.events, FakeSmtp.failure = [], [], None
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    return FakeSmtp


def make_mailer(**overrides: Any) -> EmailRegistrationMailer:
    options: dict[str, Any] = {
        "host": "mailpit",
        "port": 1025,
        "sender": "comptes@basecamp.local",
        "public_base_url": "http://localhost:8080/",
        "username": "",
        "password": "",
        "starttls": False,
        "timeout_seconds": 5.0,
    }
    options.update(overrides)
    public_base_url = options.pop("public_base_url")
    return EmailRegistrationMailer(SmtpEmailSender(**options), public_base_url)


class TestEmailRegistrationMailerOverSmtp:
    def test_verification_email_links_to_the_front_with_the_token_in_the_fragment(self) -> None:
        make_mailer().send_verification(EmailAddress.of("camille@example.com"), TOKEN)

        [message] = FakeSmtp.sent
        body = message.get_content()
        assert message["To"] == "camille@example.com"
        assert message["From"] == "comptes@basecamp.local"
        assert f"http://localhost:8080/compte/verification#token={TOKEN}" in body
        assert "?token=" not in body
        assert "24 heures" in body

    def test_account_exists_email_carries_no_token_and_no_link(self) -> None:
        make_mailer().send_account_exists(EmailAddress.of("camille@example.com"))

        [message] = FakeSmtp.sent
        assert message["To"] == "camille@example.com"
        assert "existe déjà" in message["Subject"]
        assert "http" not in message.get_content()

    def test_connects_with_the_configured_timeout_and_no_auth_by_default(self) -> None:
        make_mailer().send_account_exists(EmailAddress.of("camille@example.com"))

        assert FakeSmtp.events == ["connect:mailpit:1025:5.0"]

    def test_uses_starttls_and_login_when_configured(self) -> None:
        mailer = make_mailer(starttls=True, username="relay", password="x")

        mailer.send_account_exists(EmailAddress.of("camille@example.com"))

        assert FakeSmtp.events[1:] == ["starttls", "login:relay"]

    @pytest.mark.parametrize("error", [OSError("refused"), smtplib.SMTPException("boom")])
    def test_transport_failures_become_a_delivery_error_without_detail(
        self, error: Exception
    ) -> None:
        FakeSmtp.failure = error

        with pytest.raises(MailDeliveryError) as raised:
            make_mailer().send_verification(EmailAddress.of("camille@example.com"), TOKEN)

        assert TOKEN not in str(raised.value)
        assert raised.value.__cause__ is None
