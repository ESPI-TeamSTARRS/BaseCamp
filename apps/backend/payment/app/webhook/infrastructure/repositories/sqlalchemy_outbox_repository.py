from sqlalchemy.orm import Session

from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.interfaces.outbox_repository import OutboxRepository
from app.webhook.infrastructure.mappers.outbox_event_mapper import OutboxEventMapper


class SqlAlchemyOutboxRepository(OutboxRepository):
    """Écrit dans la session de l'appelant : l'événement partage la transaction de l'état."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: OutboxEvent) -> None:
        self._session.add(OutboxEventMapper.to_model(event))
        self._session.flush()
