from dataclasses import dataclass

from app.order.domain.enums.order_status import OrderStatus


@dataclass(frozen=True)
class PayableOrder:
    """Ce que le paiement sait d'une commande : numéro, statut et total figé (centimes)."""

    id: str
    number: str
    status: OrderStatus
    total_cents: int
