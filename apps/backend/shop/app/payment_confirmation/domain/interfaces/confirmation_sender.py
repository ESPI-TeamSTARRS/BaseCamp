from abc import ABC, abstractmethod

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail


class ConfirmationSender(ABC):
    """Port d'envoi de l'email de confirmation (adaptateur SMTP vers Mailpit en développement)."""

    @abstractmethod
    def send(self, mail: ConfirmationMail) -> None:
        """Lève ConfirmationDeliveryError si l'email ne part pas."""
