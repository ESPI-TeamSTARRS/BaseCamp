from abc import ABC, abstractmethod
from uuid import UUID

from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction


class ConfirmationSession(ABC):
    """Une transaction de base de données : tout ce qui est lu ici est verrouillé puis écrit d'un bloc."""

    @abstractmethod
    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        """Lit l'intention en posant un verrou de ligne jusqu'à la fin de la transaction."""

    @abstractmethod
    def find_record(self, caller: str, key: str) -> ConfirmationRecord | None: ...

    @abstractmethod
    def save(
        self, intent: PaymentIntent, record: ConfirmationRecord, ledger: LedgerTransaction | None
    ) -> None:
        """Écrit l'état de l'intention, la clé d'idempotence et le grand livre, atomiquement.

        Lève ConfirmationKeyReusedError si la clé a été prise par une autre demande.
        """
