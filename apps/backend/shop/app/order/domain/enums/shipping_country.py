from enum import StrEnum
from typing import Self


class ShippingCountry(StrEnum):
    """Pays de livraison acceptes (codes ISO 3166-1 alpha-2)."""

    FR = "FR"
    BE = "BE"
    CH = "CH"
    LU = "LU"
    DE = "DE"
    ES = "ES"
    IT = "IT"

    @classmethod
    def parse(cls, raw: str) -> Self | None:
        try:
            return cls(raw.strip().upper())
        except ValueError:
            return None
