# ruff: noqa: S105  (motifs et noms d'evenements : faux positifs "mot de passe" sur secret/token)
from enum import StrEnum


class DenialReason(StrEnum):
    """Motifs internes d'un refus (journal seulement : la reponse HTTP reste generique)."""

    UNKNOWN_CLIENT = "unknown_client"
    INVALID_SECRET = "invalid_secret"
    SCOPE_NOT_ALLOWED = "scope_not_allowed"
    UNKNOWN_AUDIENCE = "unknown_audience"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
