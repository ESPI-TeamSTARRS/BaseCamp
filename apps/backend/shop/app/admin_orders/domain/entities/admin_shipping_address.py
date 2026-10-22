from dataclasses import dataclass


@dataclass(frozen=True)
class AdminShippingAddress:
    """Adresse de livraison : donnee personnelle, jamais journalisee."""

    full_name: str
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country: str
