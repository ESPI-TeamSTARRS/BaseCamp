from dataclasses import dataclass
from datetime import datetime

from app.account_orders.domain.entities.account_order_line import AccountOrderLine


@dataclass(frozen=True)
class AccountOrder:
    """Commande vue par son titulaire : jamais l'email ni l'adresse, seulement ce que le compte retrouve."""

    id: str
    number: str
    status: str
    lines: tuple[AccountOrderLine, ...]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
