from enum import StrEnum


class ServiceTokenEvent(StrEnum):
    """Noms d'evenements metier de la tranche (stables : jamais renommes une fois publies)."""

    ISSUED = "auth.service_token_issued"
    DENIED = "auth.service_token_denied"
    RATE_LIMITED = "auth.service_rate_limited"
    VERIFICATION_DENIED = "auth.token_verification_denied"
    CLIENT_BOOTSTRAPPED = "auth.service_client_bootstrapped"
