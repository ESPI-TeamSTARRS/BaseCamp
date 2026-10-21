from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.webhook.__tests__.support import InMemoryDeliveryUnitOfWork, InMemoryOutbox, ScriptedSender
from app.webhook.application import webhook_event_names as names
from app.webhook.application.deliver_next_event import DeliverNextEventUseCase
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.webhook_signer import WebhookSigner
from app.webhook.domain.value_objects.delivery_result import DeliveryResult
from app.webhook.domain.value_objects.retry_policy import RetryPolicy

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
POLICY = RetryPolicy(max_attempts=2, base_seconds=1, max_delay_seconds=10)
BODY = '{"id":"e","type":"payment.failed"}'


def _dead() -> OutboxEvent:
    event = OutboxEvent.pending(uuid4(), WebhookEventType.PAYMENT_FAILED, uuid4(), BODY, NOW)
    return event.mark_failed(NOW, "http_500", POLICY).mark_failed(NOW, "http_500", POLICY)


class Fixture:
    def __init__(self) -> None:
        self.outbox = InMemoryOutbox()
        self.logger = InMemoryBusinessEventLogger()
        self.now = NOW + timedelta(hours=1)
        self.use_case = RequeueDeadEventsUseCase(
            InMemoryDeliveryUnitOfWork(self.outbox), lambda: self.now, self.logger
        )
        self.dead = _dead()
        self.other_dead = _dead()
        self.pending = OutboxEvent.pending(
            uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, uuid4(), BODY, NOW
        )
        for event in (self.dead, self.other_dead, self.pending):
            self.outbox.events[event.id] = event


class TestRequeue:
    def test_one_dead_event_goes_back_to_pending_and_due(self) -> None:
        fx = Fixture()

        count = fx.use_case.execute(fx.dead.id)

        assert count == 1
        again = fx.outbox.events[fx.dead.id]
        assert (again.status, again.attempts, again.next_attempt_at) == (
            OutboxStatus.PENDING,
            0,
            fx.now,
        )
        assert fx.outbox.events[fx.other_dead.id].status is OutboxStatus.DEAD

    def test_without_an_id_every_dead_event_is_requeued(self) -> None:
        fx = Fixture()

        assert fx.use_case.execute(None) == 2
        assert fx.outbox.events[fx.pending.id].attempts == 0

    def test_a_pending_or_unknown_event_is_not_requeued(self) -> None:
        fx = Fixture()

        assert fx.use_case.execute(fx.pending.id) == 0
        assert fx.use_case.execute(uuid4()) == 0
        assert fx.logger.events == []

    def test_each_requeue_is_logged_without_the_body(self) -> None:
        fx = Fixture()

        fx.use_case.execute(fx.dead.id)

        (event,) = fx.logger.events
        assert (event.event, event.outcome, event.reason) == (
            names.WEBHOOK_EVENT_REQUEUED,
            Outcome.SUCCESS,
            None,
        )
        assert (event.resource_type, event.resource_id) == ("webhook_event", str(fx.dead.id))
        assert (event.actor_type, event.actor_id) == ("service", "operations")
        assert BODY not in repr(event)

    def test_the_relaunched_event_keeps_its_id_and_body_so_the_shop_deduplicates(self) -> None:
        fx = Fixture()
        fx.use_case.execute(fx.dead.id)
        sender = ScriptedSender(DeliveryResult.ok(200))
        deliver = DeliverNextEventUseCase(
            InMemoryDeliveryUnitOfWork(fx.outbox),
            sender,
            WebhookSigner(["whsec_unit_0123456789abcdef0123456789abcdef"]),
            POLICY,
            lambda: fx.now,
            fx.logger,
        )
        fx.outbox.events.pop(fx.other_dead.id)

        deliver.execute()

        assert [(sent[0], sent[1]) for sent in sender.sent] == [(fx.dead.id, BODY)]
        assert fx.outbox.events[fx.dead.id].status is OutboxStatus.DELIVERED
