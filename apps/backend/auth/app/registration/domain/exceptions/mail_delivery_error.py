from app.registration.domain.exceptions.domain_exception import DomainException

SMTP_FAILURE = "smtp_error"


class MailDeliveryError(DomainException):
    """Email non remis. `cause` est un code ferme (`timeout`, `http_403`, `smtp_error`...) : jamais
    d'adresse, de lien, de secret ni de message du serveur."""

    def __init__(self, cause: str = SMTP_FAILURE) -> None:
        super().__init__("mail_delivery_failed", "Email non remis au serveur de messagerie.")
        self.cause = cause
