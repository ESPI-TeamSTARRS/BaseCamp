from app.login.domain.exceptions.domain_exception import DomainException


class EnrollmentRefusedError(DomainException):
    """Enrolement refuse : message fixe pour l'operateur du terminal, jamais de donnee biometrique."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)
