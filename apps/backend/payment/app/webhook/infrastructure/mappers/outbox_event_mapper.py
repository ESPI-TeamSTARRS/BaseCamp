from app.intent.infrastructure.mappers.payment_intent_mapper import PaymentIntentMapper
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel


class OutboxEventMapper:
    @staticmethod
    def to_entity(model: OutboxEventModel) -> OutboxEvent:
        return OutboxEvent(
            id=model.id,
            event_type=WebhookEventType(model.event_type),
            intent_id=model.intent_id,
            body=model.body,
            status=OutboxStatus(model.status),
            attempts=model.attempts,
            next_attempt_at=PaymentIntentMapper.to_utc(model.next_attempt_at),
            created_at=PaymentIntentMapper.to_utc(model.created_at),
            last_error=model.last_error,
            delivered_at=(
                PaymentIntentMapper.to_utc(model.delivered_at) if model.delivered_at else None
            ),
        )

    @staticmethod
    def to_model(event: OutboxEvent) -> OutboxEventModel:
        return OutboxEventModel(
            id=event.id,
            event_type=event.event_type.value,
            intent_id=event.intent_id,
            body=event.body,
            status=event.status.value,
            attempts=event.attempts,
            next_attempt_at=event.next_attempt_at,
            created_at=event.created_at,
            last_error=event.last_error,
            delivered_at=event.delivered_at,
        )
