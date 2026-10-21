from enum import StrEnum


class TokenRejection(StrEnum):
    """Motif interne d'un rejet (journal seulement : l'appelant recoit toujours le meme 401)."""

    MISSING = "missing_token"
    MISSING_KEY_ID = "missing_key_id"
    UNKNOWN_KEY = "unknown_key"
    BAD_ALGORITHM = "bad_algorithm"
    EXPIRED = "expired"
    INVALID = "invalid"
    WRONG_ISSUER = "wrong_issuer"
    WRONG_AUDIENCE = "wrong_audience"
    WRONG_TOKEN_USE = "wrong_token_use"  # noqa: S105


class TokenRejectedError(Exception):
    """Jeton absent ou refuse (signature, emetteur, audience, expiration, forme)."""

    def __init__(self, rejection: TokenRejection) -> None:
        super().__init__("token_rejected")
        self.rejection = rejection
