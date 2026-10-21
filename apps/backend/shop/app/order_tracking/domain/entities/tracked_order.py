from dataclasses import dataclass
from datetime import datetime

from app.order_tracking.domain.entities.tracked_line import TrackedLine


@dataclass(frozen=True)
class TrackedOrder:
    """Ce que le suivi sait d'une commande; l'email ne sert qu'à vérifier le demandeur."""

    number: str
    email: str
    status: str
    lines: tuple[TrackedLine, ...]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
