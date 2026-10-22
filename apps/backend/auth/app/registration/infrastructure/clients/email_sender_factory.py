import httpx

from app.core.config import Settings
from app.registration.domain.interfaces.email_sender import EmailSender
from app.registration.infrastructure.clients.n8n_email_sender import N8nEmailSender
from app.registration.infrastructure.clients.smtp_email_sender import SmtpEmailSender


class EmailSenderFactory:
    """Choisit le transport selon `APP_MAIL_TRANSPORT` : `smtp` (Mailpit en dev et en CI) ou `n8n`."""

    @staticmethod
    def build(settings: Settings) -> EmailSender:
        if settings.mail_transport == "n8n":
            return N8nEmailSender(
                httpx.Client(),
                settings.n8n_mail_url,
                settings.n8n_mail_secret.get_secret_value(),
                settings.n8n_mail_timeout_seconds,
            )
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value(),
            starttls=settings.smtp_starttls,
            timeout_seconds=settings.smtp_timeout_seconds,
        )
