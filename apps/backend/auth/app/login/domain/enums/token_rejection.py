from enum import StrEnum


class TokenRejection(StrEnum):
    """Motifs internes d'un rejet de jeton (jamais detailles au client)."""

    EXPIRED = "expired"
    INVALID = "invalid"
    REVOKED = "revoked"
