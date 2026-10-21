from app.registration.domain.exceptions.domain_exception import DomainException


class MailDeliveryError(DomainException):
    def __init__(self) -> None:
        super().__init__("mail_delivery_failed", "Email non remis au serveur de messagerie.")
