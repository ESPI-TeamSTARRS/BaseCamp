from app.registration.domain.exceptions.domain_exception import DomainException


class InvalidEmailError(DomainException):
    def __init__(self) -> None:
        super().__init__("email_invalid", "Adresse email invalide.")
