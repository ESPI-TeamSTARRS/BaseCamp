from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.confirmation.domain.interfaces.confirmation_session import ConfirmationSession
from app.confirmation.infrastructure.models.confirmation_key_model import ConfirmationKeyModel
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.interfaces.ledger_repository import LedgerRepository


class SqlAlchemyConfirmationSession(ConfirmationSession):
    def __init__(self, session: Session, ledger: LedgerRepository) -> None:
        self._session = session
        self._ledger = ledger

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        model = self._session.scalar(
            select(PaymentIntentModel).where(PaymentIntentModel.id == intent_id).with_for_update()
        )
        return PaymentIntentMapper.to_entity(model) if model else None

    def find_record(self, caller: str, key: str) -> ConfirmationRecord | None:
        row = self._session.get(ConfirmationKeyModel, (caller, key))
        if row is None:
            return None
        return ConfirmationRecord(row.caller, row.key, row.request_hash, row.intent_id)

    def save(
        self, intent: PaymentIntent, record: ConfirmationRecord, ledger: LedgerTransaction | None
    ) -> None:
        model = self._session.get(PaymentIntentModel, intent.id)
        if model is None:  # impossible : l'intention est verrouillée par la même transaction
            raise LookupError
        model.status = intent.status.value
        self._session.add(
            ConfirmationKeyModel(
                caller=record.caller,
                key=record.key,
                request_hash=record.request_hash,
                intent_id=record.intent_id,
            )
        )
        self._flush_key()
        if ledger:
            self._ledger.add(ledger)

    def _flush_key(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            if "confirmation_keys" in str(error.orig):
                raise ConfirmationKeyReusedError from None
            raise
