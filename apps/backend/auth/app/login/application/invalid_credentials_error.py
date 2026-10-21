from app.login.domain.exceptions.domain_exception import DomainException


class InvalidCredentialsError(DomainException):
    """Meme erreur pour email inconnu, mauvais mot de passe et compte desactive."""

    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Identifiants invalides.")
