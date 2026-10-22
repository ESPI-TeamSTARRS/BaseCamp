from abc import ABC, abstractmethod

from app.registration.domain.value_objects.email_address import EmailAddress


class EmailSender(ABC):
    """Transport d'envoi des emails du service (SMTP ou webhook n8n) : les mailers ne le connaissent pas.

    `body` est un texte brut; chaque transport le met en forme (SMTP : texte, n8n : HTML).
    """

    @abstractmethod
    def send(self, to: EmailAddress, subject: str, body: str) -> None:
        """Leve `MailDeliveryError` (avec un motif sans donnee sensible) si l'envoi echoue."""
