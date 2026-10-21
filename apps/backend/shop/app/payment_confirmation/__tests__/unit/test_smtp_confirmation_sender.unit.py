"""Adaptateur SMTP : contenu de l'email et conversion des pannes en erreur de remise."""

import smtplib
from email.message import EmailMessage
from types import TracebackType
from typing import ClassVar, Self

import pytest

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.mail_line import MailLine
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.infrastructure.senders.smtp_confirmation_sender import (
    SmtpConfirmationSender,
)

MAIL = ConfirmationMail(
    to="camille.martin@example.org",
    order_number="BC-ABCDEFGHJK",
    total_cents=4490,
    lines=(MailLine("Popote en titane", 1, 3900), MailLine("Gourde", 2, 590)),
)


class _FakeSmtp:
    sent: ClassVar[list[EmailMessage]] = []
    failure: ClassVar[Exception | None] = None
    opened: ClassVar[list[tuple[str, int, float]]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.opened.append((host, port, timeout))
        if self.failure is not None:
            raise self.failure

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def send_message(self, message: EmailMessage) -> None:
        self.sent.append(message)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[_FakeSmtp]:
    _FakeSmtp.sent, _FakeSmtp.opened, _FakeSmtp.failure = [], [], None
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    return _FakeSmtp


def _sender() -> SmtpConfirmationSender:
    return SmtpConfirmationSender("mailpit", 1025, "commandes@basecamp.local", 3.0)


class TestSmtpConfirmationSender:
    def test_sends_one_email_with_the_order_number_the_lines_and_the_total(self) -> None:
        _sender().send(MAIL)

        (message,) = _FakeSmtp.sent
        assert message["To"] == "camille.martin@example.org"
        assert message["From"] == "commandes@basecamp.local"
        assert "BC-ABCDEFGHJK" in message["Subject"]
        body = message.get_content()
        assert "BC-ABCDEFGHJK" in body
        assert "1 x Popote en titane : 39,00 EUR" in body
        assert "2 x Gourde : 5,90 EUR" in body
        assert "Total : 44,90 EUR" in body
        assert _FakeSmtp.opened == [("mailpit", 1025, 3.0)]

    @pytest.mark.parametrize(
        "failure",
        [ConnectionRefusedError(), TimeoutError(), smtplib.SMTPServerDisconnected()],
    )
    def test_a_server_that_is_down_or_slow_becomes_a_delivery_error(
        self, failure: Exception
    ) -> None:
        _FakeSmtp.failure = failure

        with pytest.raises(ConfirmationDeliveryError):
            _sender().send(MAIL)

    def test_an_address_that_cannot_be_put_in_a_header_becomes_a_delivery_error(self) -> None:
        bad = ConfirmationMail("a@b.c\r\nBcc: x@y.z", "BC-1", 100, ())

        with pytest.raises(ConfirmationDeliveryError):
            _sender().send(bad)
