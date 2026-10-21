from abc import ABC, abstractmethod
from uuid import UUID

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.refund.domain.entities.refund import Refund
from app.webhook.domain.entities.outbox_event import OutboxEvent


class RefundSession(ABC):
    """Une transaction de base de données : l'intention est verrouillée puis tout est écrit d'un bloc."""

    @abstractmethod
    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        """Lit l'intention en posant un verrou de ligne jusqu'à la fin de la transaction."""

    @abstractmethod
    def find_refund(self, caller: str, key: str) -> Refund | None: ...

    @abstractmethod
    def save(
        self,
        intent: PaymentIntent,
        refund: Refund,
        ledger: LedgerTransaction,
        outbox_event: OutboxEvent,
    ) -> None:
        """Écrit le cumul remboursé, le remboursement, le grand livre et l'événement, atomiquement.

        La base refuse elle-même tout cumul supérieur au montant capturé, quoi que fasse l'appelant.

        Lève RefundKeyReusedError si la clé a été prise par un autre remboursement.
        """
