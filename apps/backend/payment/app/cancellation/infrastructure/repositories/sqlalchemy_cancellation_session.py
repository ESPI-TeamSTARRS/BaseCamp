from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cancellation.domain.interfaces.cancellation_session import CancellationSession
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel


class SqlAlchemyCancellationSession(CancellationSession):
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        model = self._session.scalar(
            select(PaymentIntentModel).where(PaymentIntentModel.id == intent_id).with_for_update()
        )
        return PaymentIntentMapper.to_entity(model) if model else None

    def save(self, intent: PaymentIntent) -> None:
        model = self._session.get(PaymentIntentModel, intent.id)
        if model is None:  # impossible : l'intention est verrouillée par la même transaction
            raise LookupError
        model.status = intent.status.value
