import re
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.value_objects.retry_policy import RetryPolicy

_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class OutboxEvent:
    """Événement à livrer à la boutique, écrit dans la même transaction que l'état du paiement.

    L'identifiant et le corps ne changent jamais : chaque tentative envoie les mêmes octets
    (la boutique déduplique sur l'identifiant). `last_error` est un code, jamais un message.
    """

    id: UUID
    event_type: WebhookEventType
    intent_id: UUID
    body: str
    status: OutboxStatus
    attempts: int
    next_attempt_at: datetime
    created_at: datetime
    last_error: str | None = None
    delivered_at: datetime | None = None

    @classmethod
    def pending(
        cls,
        event_id: UUID,
        event_type: WebhookEventType,
        intent_id: UUID,
        body: str,
        now: datetime,
    ) -> "OutboxEvent":
        return cls(
            id=event_id,
            event_type=event_type,
            intent_id=intent_id,
            body=body,
            status=OutboxStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )

    def mark_delivered(self, now: datetime) -> "OutboxEvent":
        return replace(
            self,
            status=OutboxStatus.DELIVERED,
            attempts=self.attempts + 1,
            delivered_at=now,
            last_error=None,
        )

    def mark_failed(self, now: datetime, error_code: str, policy: RetryPolicy) -> "OutboxEvent":
        if not _ERROR_CODE.match(error_code):
            raise ValueError("last_error must be a snake_case code, not a message")
        attempts = self.attempts + 1
        if policy.is_exhausted(attempts):
            return replace(self, status=OutboxStatus.DEAD, attempts=attempts, last_error=error_code)
        return replace(
            self,
            attempts=attempts,
            last_error=error_code,
            next_attempt_at=now + policy.delay_after(attempts),
        )

    def mark_rejected(self, now: datetime, reason_code: str) -> "OutboxEvent":
        """Refus définitif de la boutique (ex. paiement après expiration de la commande) : pas de relance."""
        if not _ERROR_CODE.match(reason_code):
            raise ValueError("last_error must be a snake_case code, not a message")
        return replace(
            self,
            status=OutboxStatus.REJECTED_BY_RECEIVER,
            attempts=self.attempts + 1,
            last_error=reason_code,
        )

    def requeue(self, now: datetime) -> "OutboxEvent":
        """Relance d'exploitation d'un événement `dead` : même identifiant, nouveau budget."""
        if self.status is not OutboxStatus.DEAD:
            raise ValueError("only a dead event can be requeued")
        return replace(self, status=OutboxStatus.PENDING, attempts=0, next_attempt_at=now)
