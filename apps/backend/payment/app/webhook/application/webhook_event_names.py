"""Noms des événements du webhook sortant (catalogue : docs/services/payment.md).

Centralisés ici pour rester faciles à renommer : un nom publié ne change plus ensuite.
"""

WEBHOOK_EVENT_QUEUED = "webhook.event_queued"
WEBHOOK_DELIVERED = "webhook.delivered"
WEBHOOK_DELIVERY_FAILED = "webhook.delivery_failed"
WEBHOOK_EVENT_DEAD = "webhook.event_dead"
WEBHOOK_REJECTED_BY_RECEIVER = "webhook.rejected_by_receiver"
WEBHOOK_EVENT_REQUEUED = "webhook.event_requeued"
WEBHOOK_WORKER_FAILED = "webhook.worker_failed"
