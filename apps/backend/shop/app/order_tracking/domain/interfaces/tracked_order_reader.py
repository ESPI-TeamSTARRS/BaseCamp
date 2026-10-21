from abc import ABC, abstractmethod

from app.order_tracking.domain.entities.tracked_order import TrackedOrder


class TrackedOrderReader(ABC):
    @abstractmethod
    def find_by_number(self, number: str) -> TrackedOrder | None:
        """Commande portant ce numéro, ou None. Le coût de la lecture ne dépend pas de l'existence."""
