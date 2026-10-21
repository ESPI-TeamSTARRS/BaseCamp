from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExpirableOrder:
    """Commande en attente de paiement depuis trop longtemps."""

    id: str
    number: str
    created_at: datetime
