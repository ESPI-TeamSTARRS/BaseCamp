import httpx

from app.core.config import Settings
from app.payment_confirmation.domain.interfaces.confirmation_sender import ConfirmationSender
from app.payment_confirmation.infrastructure.senders.n8n_confirmation_sender import (
    N8nConfirmationSender,
)
from app.payment_confirmation.infrastructure.senders.smtp_confirmation_sender import (
    SmtpConfirmationSender,
)


class ConfirmationSenderFactory:
    """Choisit l'adaptateur d'envoi selon `APP_MAIL_TRANSPORT` (le port `ConfirmationSender` ne change pas)."""

    @staticmethod
    def build(settings: Settings) -> ConfirmationSender:
        if settings.mail_transport == "n8n":
            return N8nConfirmationSender(
                httpx.Client(),
                settings.n8n_mail_url,
                settings.n8n_mail_secret,
                settings.n8n_mail_timeout_seconds,
            )
        return SmtpConfirmationSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_from,
            settings.smtp_timeout_seconds,
        )
