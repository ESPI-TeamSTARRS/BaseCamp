import smtplib
from email.message import EmailMessage

from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.interfaces.email_sender import EmailSender
from app.registration.domain.value_objects.email_address import EmailAddress


class SmtpEmailSender(EmailSender):
    """Transport SMTP commun aux emails du service. Aucun detail du transport ne remonte."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        username: str,
        password: str,
        starttls: bool,
        timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._starttls = starttls
        self._timeout_seconds = timeout_seconds

    def send(self, to: EmailAddress, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to.value
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as smtp:
                if self._starttls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise MailDeliveryError from None
