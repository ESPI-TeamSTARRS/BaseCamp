from abc import ABC, abstractmethod

from app.registration.domain.value_objects.email_address import EmailAddress


class RegistrationMailer(ABC):
    @abstractmethod
    def send_verification(self, to: EmailAddress, token: str) -> None:
        """Leve MailDeliveryError si le serveur de messagerie refuse ou est injoignable."""

    @abstractmethod
    def send_account_exists(self, to: EmailAddress) -> None:
        """Previent le titulaire qu'une inscription a ete tentee avec son adresse."""
