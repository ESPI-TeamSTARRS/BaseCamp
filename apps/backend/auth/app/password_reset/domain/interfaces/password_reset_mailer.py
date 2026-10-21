from abc import ABC, abstractmethod

from app.registration.domain.value_objects.email_address import EmailAddress


class PasswordResetMailer(ABC):
    @abstractmethod
    def send_reset_link(self, to: EmailAddress, token: str) -> None:
        """Leve MailDeliveryError si le serveur de messagerie refuse ou est injoignable."""

    @abstractmethod
    def send_password_changed(self, to: EmailAddress) -> None:
        """Previent le titulaire que son mot de passe vient d'etre remplace."""
