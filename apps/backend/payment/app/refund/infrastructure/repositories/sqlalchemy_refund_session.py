from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.value_objects.amount import Amount
from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.interfaces.ledger_repository import LedgerRepository
from app.refund.domain.entities.refund import Refund
from app.refund.domain.exceptions.refund_key_reused_error import RefundKeyReusedError
from app.refund.domain.interfaces.refund_session import RefundSession
from app.refund.infrastructure.models.refund_model import RefundModel
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.interfaces.outbox_repository import OutboxRepository

_KEY_CONSTRAINT = "uq_refunds_caller_key"
_KEY_COLUMNS = "refunds.caller, refunds.idempotency_key"  # message de SQLite


class SqlAlchemyRefundSession(RefundSession):
    def __init__(
        self, session: Session, ledger: LedgerRepository, outbox: OutboxRepository
    ) -> None:
        self._session = session
        self._ledger = ledger
        self._outbox = outbox

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        model = self._session.scalar(
            select(PaymentIntentModel).where(PaymentIntentModel.id == intent_id).with_for_update()
        )
        return PaymentIntentMapper.to_entity(model) if model else None

    def find_refund(self, caller: str, key: str) -> Refund | None:
        row = self._session.scalar(
            select(RefundModel).where(
                RefundModel.caller == caller, RefundModel.idempotency_key == key
            )
        )
        if row is None:
            return None
        return Refund(
            id=row.id,
            intent_id=row.intent_id,
            amount=Amount(row.amount),
            amount_refunded=row.amount_refunded,
            caller=row.caller,
            key=row.idempotency_key,
            request_hash=row.request_hash,
            created_at=PaymentIntentMapper.to_utc(row.created_at),
        )

    def save(
        self,
        intent: PaymentIntent,
        refund: Refund,
        ledger: LedgerTransaction,
        outbox_event: OutboxEvent,
    ) -> None:
        model = self._session.get(PaymentIntentModel, intent.id)
        if model is None:  # impossible : l'intention est verrouillée par la même transaction
            raise LookupError
        model.refunded_amount = intent.refunded_amount
        self._session.add(
            RefundModel(
                id=refund.id,
                intent_id=refund.intent_id,
                amount=refund.amount.cents,
                amount_refunded=refund.amount_refunded,
                caller=refund.caller,
                idempotency_key=refund.key,
                request_hash=refund.request_hash,
                created_at=refund.created_at,
            )
        )
        self._flush_refund()
        self._ledger.add(ledger)
        self._outbox.add(outbox_event)

    def _flush_refund(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            message = str(error.orig)
            if _KEY_CONSTRAINT in message or _KEY_COLUMNS in message:
                raise RefundKeyReusedError from None
            raise
