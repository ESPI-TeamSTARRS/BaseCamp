from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.domain_exception import DomainException


class AccessTokenRejectedError(DomainException):
    """Jeton refuse : le motif sert aux journaux, le client recoit toujours la meme reponse."""

    def __init__(self, rejection: TokenRejection) -> None:
        super().__init__("access_token_rejected", "Authentification requise.")
        self.rejection = rejection
