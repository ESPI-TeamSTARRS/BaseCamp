from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.interfaces.webhook_events import WebhookEvents
from app.payment_confirmation.infrastructure.models.payment_webhook_event_model import (
    PaymentWebhookEventModel,
)


class SqlAlchemyWebhookEvents(WebhookEvents):
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, event_id: str) -> bool:
        return (
            self._session.scalars(
                select(PaymentWebhookEventModel.id).where(PaymentWebhookEventModel.id == event_id)
            ).first()
            is not None
        )

    def is_order_confirmed(self, order_id: str) -> bool:
        return (
            self._session.scalars(
                select(PaymentWebhookEventModel.id).where(
                    PaymentWebhookEventModel.paid_order_id == order_id
                )
            ).first()
            is not None
        )

    def record(
        self,
        event_id: str,
        event_type: str,
        outcome: WebhookOutcome,
        reason: str | None,
        confirmed_order_id: str | None,
    ) -> None:
        self._session.add(
            PaymentWebhookEventModel(
                id=event_id,
                event_type=event_type,
                outcome=outcome.value,
                reason=reason,
                paid_order_id=confirmed_order_id,
                received_at=datetime.now(UTC),
            )
        )
