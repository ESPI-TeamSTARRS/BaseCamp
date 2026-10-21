from abc import ABC, abstractmethod

from app.payment_confirmation.domain.entities.confirmation_mail import ConfirmationMail
from app.payment_confirmation.domain.entities.settlement_target import SettlementTarget


class SettlementTargets(ABC):
    @abstractmethod
    def find_for_update(self, reference: str) -> SettlementTarget | None:
        """Commande et tentative de cette référence, commande verrouillée (FOR UPDATE)."""

    @abstractmethod
    def mark_paid(self, order_id: str) -> None: ...

    @abstractmethod
    def set_attempt_status(self, attempt_id: str, status: str) -> None: ...

    @abstractmethod
    def commit_reservations(self, order_id: str) -> int:
        """Rend définitives les réservations de stock encore « reserved »; renvoie leur nombre."""

    @abstractmethod
    def mail_for(self, order_id: str) -> ConfirmationMail: ...
