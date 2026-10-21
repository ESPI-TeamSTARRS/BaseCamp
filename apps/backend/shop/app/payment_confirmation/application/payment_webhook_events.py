from app.core.events.business_event import BusinessEvent
from app.payment_confirmation.domain.entities.payment_event import PaymentEvent

CURRENCY = "EUR"
WEBHOOK_RECEIVED = "payment.webhook_received"
WEBHOOK_REJECTED = "payment.webhook_rejected"
WEBHOOK_REPLAYED = "payment.webhook_replayed"
WEBHOOK_IGNORED = "payment.webhook_ignored"
ORDER_PAYMENT_FAILED = "order.payment_failed"
ORDER_REFUNDED = "order.refunded"
CONFIRMATION_EMAIL_SENT = "order.confirmation_email_sent"
CONFIRMATION_EMAIL_FAILED = "order.confirmation_email_failed"


def rejected(reason: str) -> BusinessEvent:
    """Webhook refusé (401 ou 400) : on ne journalise ni le corps ni la signature reçus."""
    return BusinessEvent.denied(WEBHOOK_REJECTED, reason)


def received(event: PaymentEvent) -> BusinessEvent:
    return BusinessEvent.success(
        WEBHOOK_RECEIVED,
        attributes={"event_id": event.event_id, "event_type": event.event_type},
    )


def replayed(event: PaymentEvent) -> BusinessEvent:
    return BusinessEvent.success(
        WEBHOOK_REPLAYED,
        attributes={"event_id": event.event_id, "event_type": event.event_type},
    )


def ignored(event: PaymentEvent, reason: str, order_number: str | None) -> BusinessEvent:
    attributes = {"event_id": event.event_id, "event_type": event.event_type}
    if order_number is None:
        return BusinessEvent.denied(WEBHOOK_IGNORED, reason, attributes=attributes)
    return BusinessEvent.denied(
        WEBHOOK_IGNORED,
        reason,
        resource_type="order",
        resource_id=order_number,
        attributes=attributes,
    )
