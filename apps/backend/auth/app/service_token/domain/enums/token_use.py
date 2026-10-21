from enum import StrEnum


class TokenUse(StrEnum):
    """Nature d'un jeton (claim `token_use`) : empêche d'utiliser un jeton à la place d'un autre."""

    SERVICE = "service"
    CLIENT = "client"
