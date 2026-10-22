from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminOrderSummary:
    """Ligne de la liste des commandes : sans adresse de livraison ni detail des lignes."""

    id: str
    number: str
    status: str
    email: str
    total_cents: int
    item_count: int
    created_at: datetime
