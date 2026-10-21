"""Noms des événements du webhook sortant (catalogue : docs/services/payment.md).

Centralisés ici pour rester faciles à renommer : un nom publié ne change plus ensuite.
"""

WEBHOOK_EVENT_QUEUED = "webhook.event_queued"
WEBHOOK_DELIVERED = "webhook.delivered"
WEBHOOK_DELIVERY_FAILED = "webhook.delivery_failed"
WEBHOOK_EVENT_DEAD = "webhook.event_dead"
WEBHOOK_EVENT_REQUEUED = "webhook.event_requeued"
