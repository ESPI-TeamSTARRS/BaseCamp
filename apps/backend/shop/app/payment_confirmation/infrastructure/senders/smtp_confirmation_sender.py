import smtplib
from email.message import EmailMessage

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.errors.confirmation_delivery_error import (
    ConfirmationDeliveryError,
)
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender


def _euros(cents: int) -> str:
    whole, fraction = divmod(cents, 100)
    return f"{whole},{fraction:02d} EUR"


class SmtpConfirmationSender(ConfirmationSender):
    """Adaptateur SMTP (Mailpit en développement, sans relais externe ni authentification)."""

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
            message["Subject"] = f"Commande {mail.order_number} confirmée"
            message.set_content(self._body(mail))
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException, ValueError):
            raise ConfirmationDeliveryError from None

    @staticmethod
    def _body(mail: ConfirmationMail) -> str:
        lines = [
            f"- {line.quantity} x {line.name} : {_euros(line.line_total_cents)}"
            for line in mail.lines
        ]
        return "\n".join(
            [
                "Bonjour,",
                "",
                f"Votre paiement est confirmé. Numéro de commande : {mail.order_number}",
                *lines,
                "",
                f"Total : {_euros(mail.total_cents)}",
                "",
                "L'équipe Basecamp",
            ]
        )
