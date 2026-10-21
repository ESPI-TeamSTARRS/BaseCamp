from enum import StrEnum


class WebhookOutcome(StrEnum):
    APPLIED = "applied"
    IGNORED = "ignored"
    REPLAYED = "replayed"
    REJECTED = "rejected"  # paiement reçu après l'expiration de la commande : 409, à rembourser
