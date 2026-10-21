from enum import StrEnum


class WebhookEventType(StrEnum):
    """Types publiés vers la boutique : un nom publié ne change plus."""

    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
