from enum import StrEnum


class TokenKind(StrEnum):
    """Famille d'un jeton d'`auth` (claim `token_use`)."""

    SERVICE = "service"
    CLIENT = "client"
