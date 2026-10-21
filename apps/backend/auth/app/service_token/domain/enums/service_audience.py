from enum import StrEnum


class ServiceAudience(StrEnum):
    """Services destinataires d'un jeton de service (liste fermée)."""

    PAYMENT = "payment"
