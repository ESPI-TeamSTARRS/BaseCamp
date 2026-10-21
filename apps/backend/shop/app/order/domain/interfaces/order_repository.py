from abc import ABC, abstractmethod

from app.order.domain.entities.order import Order


class OrderRepository(ABC):
    @abstractmethod
    def find_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        """Commande deja creee avec cette cle, ou None."""

    @abstractmethod
    def add(self, order: Order) -> None:
        """Enregistre la commande et ses lignes (ecrite au commit de l'unite de travail)."""
