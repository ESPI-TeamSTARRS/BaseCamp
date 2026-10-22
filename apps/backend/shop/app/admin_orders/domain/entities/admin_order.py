from dataclasses import dataclass
from datetime import datetime

from app.admin_orders.domain.entities.admin_order_line import AdminOrderLine
from app.admin_orders.domain.entities.admin_shipping_address import AdminShippingAddress


@dataclass(frozen=True)
class AdminOrder:
    """Commande vue par l'operateur : lignes, adresse de livraison, totaux et statut."""

    id: str
    number: str
    status: str
    email: str
    shipping_address: AdminShippingAddress
    lines: tuple[AdminOrderLine, ...]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
