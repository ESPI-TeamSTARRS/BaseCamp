from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.interfaces.delivery_session import DeliverySession
from app.webhook.infrastructure.mappers.outbox_event_mapper import OutboxEventMapper
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel


class SqlAlchemyDeliverySession(DeliverySession):
    def __init__(self, session: Session) -> None:
        self._session = session

    def claim_next_due(self, now: datetime) -> OutboxEvent | None:
        # SKIP LOCKED : un événement en cours de livraison chez un autre worker est ignoré.
        model = self._session.scalar(
            select(OutboxEventModel)
            .where(
                OutboxEventModel.status == OutboxStatus.PENDING.value,
                OutboxEventModel.next_attempt_at <= now,
            )
            .order_by(OutboxEventModel.next_attempt_at, OutboxEventModel.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return OutboxEventMapper.to_entity(model) if model else None

    def save(self, event: OutboxEvent) -> None:
        model = self._session.get(OutboxEventModel, event.id)
        if model is None:  # impossible : l'événement vient d'être réservé par cette transaction
            raise LookupError
        model.status = event.status.value
        model.attempts = event.attempts
        model.next_attempt_at = event.next_attempt_at
        model.last_error = event.last_error
        model.delivered_at = event.delivered_at

    def find_dead(self, event_id: UUID | None) -> list[OutboxEvent]:
        query = select(OutboxEventModel).where(OutboxEventModel.status == OutboxStatus.DEAD.value)
        if event_id is not None:
            query = query.where(OutboxEventModel.id == event_id)
        query = query.order_by(OutboxEventModel.created_at).with_for_update(skip_locked=True)
        return [OutboxEventMapper.to_entity(model) for model in self._session.scalars(query)]
