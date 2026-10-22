"""Sélection de l'adaptateur d'envoi selon APP_MAIL_TRANSPORT."""

from app.core.config import Settings
from app.payment_confirmation.infrastructure.senders.confirmation_sender_factory import (
    ConfirmationSenderFactory,
)
from app.payment_confirmation.infrastructure.senders.n8n_confirmation_sender import (
    N8nConfirmationSender,
)
from app.payment_confirmation.infrastructure.senders.smtp_confirmation_sender import (
    SmtpConfirmationSender,
)


class TestConfirmationSenderFactory:
    def test_smtp_by_default(self) -> None:
        assert isinstance(ConfirmationSenderFactory.build(Settings()), SmtpConfirmationSender)

    def test_n8n_when_selected(self) -> None:
        settings = Settings(
            mail_transport="n8n",
            n8n_mail_url="https://flux.example.test/webhook/send-email",
            n8n_mail_secret="valeur-de-test",  # noqa: S106
        )

        assert isinstance(ConfirmationSenderFactory.build(settings), N8nConfirmationSender)
