from abc import ABC, abstractmethod

from app.payment_request.domain.entities.payment_attempt import PaymentAttempt


class PaymentAttempts(ABC):
    @abstractmethod
    def list_for_order(self, order_id: str) -> list[PaymentAttempt]:
        """Tentatives de la commande, de la première à la dernière."""

    @abstractmethod
    def add(self, attempt: PaymentAttempt) -> None: ...

    @abstractmethod
    def set_status(self, attempt_id: str, status: str) -> None: ...
