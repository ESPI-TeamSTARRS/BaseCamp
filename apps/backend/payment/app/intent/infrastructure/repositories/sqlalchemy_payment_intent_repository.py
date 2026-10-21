from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intent.domain.entities.idempotency_record import IdempotencyRecord
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.exceptions.duplicate_order_reference_error import (
    DuplicateOrderReferenceError,
)
from app.intent.domain.exceptions.idempotency_race_error import IdempotencyRaceError
from app.intent.domain.interfaces.payment_intent_repository import PaymentIntentRepository
from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.intent.infrastructure.models.idempotency_key_model import IdempotencyKeyModel
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel


def _to_idempotency_model(record: IdempotencyRecord, created_at: datetime) -> IdempotencyKeyModel:
    return IdempotencyKeyModel(
        caller=record.caller,
        key=record.key,
        request_hash=record.request_hash,
        intent_id=record.intent_id,
        created_at=created_at,
    )


class SqlAlchemyPaymentIntentRepository(PaymentIntentRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, intent: PaymentIntent, record: IdempotencyRecord) -> None:
        with Session(self._engine) as session:
            session.add(PaymentIntentMapper.to_model(intent))
            try:
                session.flush()  # l'intention doit exister avant la clé qui la référence
                session.add(_to_idempotency_model(record, intent.created_at))
                session.commit()
            except IntegrityError as error:
                session.rollback()
                detail = str(error.orig)
                if "order_reference" in detail:
                    raise DuplicateOrderReferenceError from None
                if "idempotency_keys" in detail:
                    raise IdempotencyRaceError from None
                raise

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
            return record, PaymentIntentMapper.to_entity(intent)

    def get_by_id(self, intent_id: UUID) -> PaymentIntent | None:
        with Session(self._engine) as session:
            model = session.get(PaymentIntentModel, intent_id)
            return PaymentIntentMapper.to_entity(model) if model else None

    def get_by_order_reference(self, order_reference: str) -> PaymentIntent | None:
        with Session(self._engine) as session:
            model = session.scalar(
                select(PaymentIntentModel).where(
                    PaymentIntentModel.order_reference == order_reference
                )
            )
            return PaymentIntentMapper.to_entity(model) if model else None
