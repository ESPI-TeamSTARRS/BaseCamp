"""Doublures partagées par les tests de la tranche webhook (pas un test)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.interfaces.delivery_session import DeliverySession
from app.webhook.domain.interfaces.delivery_unit_of_work import DeliveryUnitOfWork
from app.webhook.domain.interfaces.webhook_sender import WebhookSender
from app.webhook.domain.value_objects.delivery_result import DeliveryResult


class InMemoryOutbox:
    def __init__(self) -> None:
        self.events: dict[UUID, OutboxEvent] = {}
        self.commits = 0


class InMemoryDeliverySession(DeliverySession):
    def __init__(self, outbox: InMemoryOutbox) -> None:
        self._outbox = outbox

    def claim_next_due(self, now: datetime) -> OutboxEvent | None:
        due = [
            event
            for event in self._outbox.events.values()
            if event.status is OutboxStatus.PENDING and event.next_attempt_at <= now
        ]
        return min(due, key=lambda event: event.next_attempt_at) if due else None

    def save(self, event: OutboxEvent) -> None:
        self._outbox.events[event.id] = event

    def find_dead(self, event_id: UUID | None) -> list[OutboxEvent]:
        return [
            event
            for event in self._outbox.events.values()
            if event.status is OutboxStatus.DEAD and event_id in (None, event.id)
        ]


class InMemoryDeliveryUnitOfWork(DeliveryUnitOfWork):
    def __init__(self, outbox: InMemoryOutbox) -> None:
        self._outbox = outbox

    @contextmanager
    def begin(self) -> Iterator[DeliverySession]:
        yield InMemoryDeliverySession(self._outbox)
        self._outbox.commits += 1


class ScriptedSender(WebhookSender):
    """Répond selon un scénario (un résultat par appel) et garde ce qui a été envoyé."""

    def __init__(self, *results: DeliveryResult) -> None:
        self._results: Iterator[DeliveryResult] = iter(results)
        self.sent: list[tuple[UUID, str, str]] = []

    def send(self, event_id: UUID, body: str, signature: str) -> DeliveryResult:
        self.sent.append((event_id, body, signature))
        return next(self._results)
