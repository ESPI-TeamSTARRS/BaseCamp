import smtplib
from email.message import EmailMessage

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender
from app.payment_confirmation.infrastructure.senders.confirmation_mail_text import (
    ConfirmationMailText,
)
from app.payment_confirmation.infrastructure.senders.mail_html import MailHtml


class SmtpConfirmationSender(ConfirmationSender):
    """Adaptateur SMTP (Mailpit en développement et en CI) : texte brut et alternative HTML."""

    def __init__(self, host: str, port: int, sender: str, timeout_seconds: float) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._timeout = timeout_seconds

    def send(self, mail: ConfirmationMail) -> None:
        try:
            message = EmailMessage()
            message["From"] = self._sender
            message["To"] = mail.to
            message["Subject"] = ConfirmationMailText.subject(mail)
            text = ConfirmationMailText.body(mail)
            message.set_content(text)
            message.add_alternative(MailHtml.from_text(text), subtype="html")
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException, ValueError):
            raise ConfirmationDeliveryError from None
