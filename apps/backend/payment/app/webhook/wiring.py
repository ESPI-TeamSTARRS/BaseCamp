from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.refund.application.refund_expired_order import RefundExpiredOrderUseCase
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.refund.infrastructure.repositories.sqlalchemy_refund_unit_of_work import (
    SqlAlchemyRefundUnitOfWork,
)
from app.webhook.application.deliver_next_event import DeliverNextEventUseCase
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.domain.services.webhook_signer import WebhookSigner
from app.webhook.domain.value_objects.retry_policy import RetryPolicy
from app.webhook.infrastructure.repositories.sqlalchemy_delivery_unit_of_work import (
    SqlAlchemyDeliveryUnitOfWork,
)
from app.webhook.infrastructure.senders.http_webhook_sender import HttpWebhookSender


def build_deliver_use_case(
    engine: Engine, settings: Settings, events: BusinessEventLogger
) -> DeliverNextEventUseCase:
    """Assemble la livraison : exige l'URL de la boutique et au moins un secret (environnement)."""
    return DeliverNextEventUseCase(
        SqlAlchemyDeliveryUnitOfWork(engine),
        HttpWebhookSender(settings.webhook_url, settings.webhook_timeout_seconds),
        WebhookSigner(settings.webhook_secrets),
        RetryPolicy(
            max_attempts=settings.webhook_max_attempts,
            base_seconds=settings.webhook_backoff_base_seconds,
            max_delay_seconds=settings.webhook_backoff_max_seconds,
        ),
        lambda: datetime.now(UTC),
        events,
        RefundExpiredOrderUseCase(
            RefundPaymentUseCase(
                SqlAlchemyRefundUnitOfWork(engine), lambda: datetime.now(UTC), events
            )
        ),
    )


def build_requeue_use_case(engine: Engine, events: BusinessEventLogger) -> RequeueDeadEventsUseCase:
    return RequeueDeadEventsUseCase(
        SqlAlchemyDeliveryUnitOfWork(engine), lambda: datetime.now(UTC), events
    )
