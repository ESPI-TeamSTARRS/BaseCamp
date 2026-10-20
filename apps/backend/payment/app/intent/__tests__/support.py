"""Doublures partagees par les tests de la tranche intent (pas un test)."""

from uuid import UUID

from app.intent.application.commands.create_payment_intent_command import (
    CreatePaymentIntentCommand,
)
from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository

LIMIT = 500_000


class InMemoryRepository(PaymentIntentRepository):
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.records: dict[tuple[str, str], IdempotencyRecord] = {}

    def add(self, intent: PaymentIntent, record: IdempotencyRecord) -> None:
        if any(i.order_reference == intent.order_reference for i in self.intents.values()):
            raise DuplicateOrderReferenceError
        self.intents[intent.id] = intent
        self.records[(record.caller, record.key)] = record

    def find_by_idempotency(
        self, caller: str, key: str
    ) -> tuple[IdempotencyRecord, PaymentIntent] | None:
        record = self.records.get((caller, key))
        return (record, self.intents[record.intent_id]) if record else None

    def get_by_id(self, intent_id: UUID) -> PaymentIntent | None:
        return self.intents.get(intent_id)

    def get_by_order_reference(self, order_reference: str) -> PaymentIntent | None:
        return next(
            (i for i in self.intents.values() if i.order_reference == order_reference), None
        )


def make_command(**overrides: object) -> CreatePaymentIntentCommand:
    values: dict[str, object] = {
        "caller": "shop",
        "idempotency_key": "key-0001",
        "order_reference": "CMD-1",
        "amount": 2500,
        "currency": "EUR",
    }
    values.update(overrides)
    return CreatePaymentIntentCommand(**values)  # type: ignore[arg-type]
