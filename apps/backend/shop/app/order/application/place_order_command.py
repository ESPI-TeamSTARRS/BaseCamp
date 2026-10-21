import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceOrderCommand:
    """Demande de commande : seuls productId et quantite viennent du client, jamais un prix."""

    idempotency_key: str
    email: str
    full_name: str
    address_line1: str
    address_line2: str | None
    postal_code: str
    city: str
    country: str
    items: tuple[tuple[str, int], ...]
    customer_id: str | None = None  # compte connecte (jeton verifie), nul pour un invite

    @property
    def fingerprint(self) -> str:
        """Empreinte du contenu (independante de l'ordre des lignes) pour detecter une cle reutilisee."""
        content = {
            "email": self.email.strip().lower(),
            "name": self.full_name.strip(),
            "line1": self.address_line1.strip(),
            "line2": (self.address_line2 or "").strip(),
            "postal_code": self.postal_code.strip(),
            "city": self.city.strip(),
            "country": self.country.strip().upper(),
            "items": sorted(self.items),
        }
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode("utf-8")).hexdigest()
