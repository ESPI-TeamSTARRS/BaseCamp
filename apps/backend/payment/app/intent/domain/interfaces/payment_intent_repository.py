from abc import ABC, abstractmethod
from uuid import UUID

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent


class PaymentIntentRepository(ABC):
    @abstractmethod
    def add(self, intent: PaymentIntent, record: IdempotencyRecord) -> None:
        """Enregistre l'intention et sa clé d'idempotence en une seule transaction.

        Lève DuplicateOrderReferenceError si la commande a déjà une intention et
        IdempotencyRaceError si la clé a été prise entre-temps.
        """

    @abstractmethod
    def find_by_idempotency(
        self, caller: str, key: str
    ) -> tuple[IdempotencyRecord, PaymentIntent] | None: ...

    @abstractmethod
    def get_by_id(self, intent_id: UUID) -> PaymentIntent | None: ...

    @abstractmethod
    def get_by_order_reference(self, order_reference: str) -> PaymentIntent | None: ...
