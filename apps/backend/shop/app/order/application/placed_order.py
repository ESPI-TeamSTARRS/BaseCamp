from dataclasses import dataclass

from app.order.domain.entities.order import Order


@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    created: bool  # False : rejeu idempotent, la commande existait deja
