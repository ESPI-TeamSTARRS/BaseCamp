from app.registration.domain.exceptions.domain_exception import DomainException


class EmailAlreadyRegisteredError(DomainException):
    def __init__(self) -> None:
        super().__init__("email_already_registered", "Un compte existe déjà pour cette adresse.")
