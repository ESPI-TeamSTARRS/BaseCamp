from enum import StrEnum


class TokenRejection(StrEnum):
    """Motif interne d'un rejet (journal seulement : le client recoit toujours la meme reponse)."""

    MISSING_KEY_ID = "missing_key_id"
    UNKNOWN_KEY = "unknown_key"
    BAD_ALGORITHM = "bad_algorithm"
    EXPIRED = "expired"
    INVALID = "invalid"
    WRONG_ISSUER = "wrong_issuer"
    WRONG_AUDIENCE = "wrong_audience"
    NOT_A_CLIENT_TOKEN = "not_a_client_token"  # noqa: S105


class ClientTokenRejectedError(Exception):
    """Jeton refuse (signature, emetteur, audience, expiration, forme) : une seule erreur."""

    def __init__(self, rejection: TokenRejection) -> None:
        super().__init__("client_token_rejected")
        self.rejection = rejection
