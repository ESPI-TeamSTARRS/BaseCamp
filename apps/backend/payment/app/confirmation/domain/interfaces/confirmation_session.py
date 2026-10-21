from abc import ABC, abstractmethod
from uuid import UUID

from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.webhook.domain.entities.outbox_event import OutboxEvent


class ConfirmationSession(ABC):
    """Une transaction de base de données : tout ce qui est lu ici est verrouillé puis écrit d'un bloc."""

    @abstractmethod
    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        """Lit l'intention en posant un verrou de ligne jusqu'à la fin de la transaction."""

    @abstractmethod
    def find_record(self, caller: str, key: str) -> ConfirmationRecord | None: ...

    @abstractmethod
    def save(
        self,
        intent: PaymentIntent,
        record: ConfirmationRecord,
        ledger: LedgerTransaction | None,
        outbox_event: OutboxEvent,
    ) -> None:
        """Écrit l'état, la clé d'idempotence, le grand livre et l'événement à publier, atomiquement.

        L'événement du webhook est dans la même transaction que le changement d'état : jamais
        d'événement sans état, ni d'état sans événement.

        Lève ConfirmationKeyReusedError si la clé a été prise par une autre demande.
        """
