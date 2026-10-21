from app.core.events.business_event import BusinessEvent

CURRENCY = "EUR"
PAYMENT_REQUESTED = "order.payment_requested"
PAYMENT_REJECTED = "order.payment_rejected"
PAYMENT_UNAVAILABLE = "order.payment_unavailable"
ORDER_PAID = "order.paid"
PAYMENT_FAILED = "order.payment_failed"


def rejected(reason: str, order_number: str | None = None) -> BusinessEvent:
    """Refus métier (commande introuvable, déjà payée, expirée…) : jamais l'identifiant reçu."""
    if order_number is None:
        return BusinessEvent.denied(PAYMENT_REJECTED, reason)
    return BusinessEvent.denied(
        PAYMENT_REJECTED, reason, resource_type="order", resource_id=order_number
    )


def unavailable(order_number: str) -> BusinessEvent:
    return BusinessEvent.error(
        PAYMENT_UNAVAILABLE,
        "payment_unavailable",
        resource_type="order",
        resource_id=order_number,
    )
