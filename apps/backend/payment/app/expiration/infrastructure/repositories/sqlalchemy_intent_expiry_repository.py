from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.expiration.domain.interfaces.intent_expiry_repository import IntentExpiryRepository
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel


class SqlAlchemyIntentExpiryRepository(IntentExpiryRepository):
    """Verrouille les lignes en retard (`FOR UPDATE SKIP LOCKED`) puis les expire, d'un bloc.

    Une confirmation ou une annulation qui tient déjà le verrou n'est jamais écrasée : la ligne est
    sautée. Inversement, une confirmation qui arrive pendant l'expiration attend le verrou, relit
    `expired` et reçoit 409.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def expire_overdue(self, now: datetime, limit: int) -> list[PaymentIntent]:
        with Session(self._engine) as session:
            models = session.scalars(
                select(PaymentIntentModel)
                .where(
                    PaymentIntentModel.status == IntentStatus.REQUIRES_CONFIRMATION.value,
                    PaymentIntentModel.expires_at <= now,
                )
                .order_by(PaymentIntentModel.expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for model in models:
                model.status = IntentStatus.EXPIRED.value
            session.commit()
            return [PaymentIntentMapper.to_entity(model) for model in models]
