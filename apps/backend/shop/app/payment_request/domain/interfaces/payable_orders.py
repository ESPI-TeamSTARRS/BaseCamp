from abc import ABC, abstractmethod

from app.payment_request.domain.entities.payable_order import PayableOrder


class PayableOrders(ABC):
    @abstractmethod
    def find_for_update(self, order_id: str) -> PayableOrder | None:
        """Commande verrouillée (FOR UPDATE) pour la durée de la transaction, ou None."""

    @abstractmethod
    def mark_paid(self, order_id: str) -> None:
        """Passe la commande à « payée » (écrit au commit)."""
