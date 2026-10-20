from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_race_error import IdempotencyRaceError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.models.idempotency_key_model import IdempotencyKeyModel
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel


def _utc(value: datetime) -> datetime:
    """Certains moteurs (SQLite) renvoient des dates sans fuseau : tout est en UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_entity(model: PaymentIntentModel) -> PaymentIntent:
    return PaymentIntent(
        id=model.id,
        order_reference=model.order_reference,
        amount=Amount(model.amount),
        currency=Currency(model.currency),
        status=IntentStatus(model.status),
        refunded_amount=model.refunded_amount,
        expires_at=_utc(model.expires_at),
        created_at=_utc(model.created_at),
    )


class SqlAlchemyPaymentIntentRepository(PaymentIntentRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, intent: PaymentIntent, record: IdempotencyRecord) -> None:
        with Session(self._engine) as session:
            session.add(
                PaymentIntentModel(
                    id=intent.id,
                    order_reference=intent.order_reference,
                    amount=intent.amount.cents,
                    currency=intent.currency.value,
                    status=intent.status.value,
                    refunded_amount=intent.refunded_amount,
                    expires_at=intent.expires_at,
                    created_at=intent.created_at,
                )
            )
            session.add(
                IdempotencyKeyModel(
                    caller=record.caller,
                    key=record.key,
                    request_hash=record.request_hash,
                    intent_id=record.intent_id,
                    created_at=intent.created_at,
                )
            )
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                if "order_reference" in str(error.orig):
                    raise DuplicateOrderReferenceError from None
                raise IdempotencyRaceError from None

    def find_by_idempotency(
        self, caller: str, key: str
    ) -> tuple[IdempotencyRecord, PaymentIntent] | None:
        with Session(self._engine) as session:
            row = session.get(IdempotencyKeyModel, (caller, key))
            if row is None:
                return None
            intent = session.get(PaymentIntentModel, row.intent_id)
            if intent is None:  # impossible : clé étrangère
                return None
            record = IdempotencyRecord(row.caller, row.key, row.request_hash, row.intent_id)
            return record, _to_entity(intent)

    def get_by_id(self, intent_id: UUID) -> PaymentIntent | None:
        with Session(self._engine) as session:
            model = session.get(PaymentIntentModel, intent_id)
            return _to_entity(model) if model else None

    def get_by_order_reference(self, order_reference: str) -> PaymentIntent | None:
        with Session(self._engine) as session:
            model = session.scalar(
                select(PaymentIntentModel).where(
                    PaymentIntentModel.order_reference == order_reference
                )
            )
            return _to_entity(model) if model else None
