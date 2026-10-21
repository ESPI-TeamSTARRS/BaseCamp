from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.webhook.__tests__.support import InMemoryDeliveryUnitOfWork, InMemoryOutbox, ScriptedSender
from app.webhook.application import webhook_event_names as names
from app.webhook.application.deliver_next_event import DeliverNextEventUseCase
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.webhook_signer import WebhookSigner
from app.webhook.domain.value_objects.delivery_result import DeliveryResult
from app.webhook.domain.value_objects.retry_policy import RetryPolicy

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
SECRET = "whsec_unit_0123456789abcdef0123456789abcdef"
BODY = '{"id":"e","type":"payment.succeeded"}'
POLICY = RetryPolicy(max_attempts=3, base_seconds=10, max_delay_seconds=100)


class Fixture:
    def __init__(self, *results: DeliveryResult) -> None:
        self.outbox = InMemoryOutbox()
        self.sender = ScriptedSender(*results)
        self.logger = InMemoryBusinessEventLogger()
        self.now = NOW
        self.use_case = DeliverNextEventUseCase(
            InMemoryDeliveryUnitOfWork(self.outbox),
            self.sender,
            WebhookSigner([SECRET]),
            POLICY,
            lambda: self.now,
            self.logger,
        )
        self.event = OutboxEvent.pending(
            uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, uuid4(), BODY, NOW
        )
        self.outbox.events[self.event.id] = self.event

    def stored(self) -> OutboxEvent:
        return self.outbox.events[self.event.id]


OK = DeliveryResult.ok(200)


class TestDelivery:
    def test_without_a_due_event_nothing_is_sent(self) -> None:
        fx = Fixture()
        fx.outbox.events.clear()

        assert fx.use_case.execute() is False
        assert fx.sender.sent == []
        assert fx.logger.events == []

    def test_a_due_event_is_posted_signed_with_its_own_id_and_marked_delivered(self) -> None:
        fx = Fixture(OK)

        assert fx.use_case.execute() is True

        (event_id, body, signature) = fx.sender.sent[0]
        assert (event_id, body) == (fx.event.id, BODY)
        assert WebhookSigner([SECRET]).verify(signature, BODY, now=int(NOW.timestamp()))
        assert fx.stored().status is OutboxStatus.DELIVERED
        assert fx.stored().delivered_at == NOW

    def test_an_event_that_is_not_yet_due_is_left_alone(self) -> None:
        fx = Fixture()
        fx.outbox.events[fx.event.id] = fx.event.mark_failed(NOW, "http_500", POLICY)

        assert fx.use_case.execute() is False
        assert fx.sender.sent == []

    def test_a_delivered_event_is_never_sent_again(self) -> None:
        fx = Fixture(OK)
        fx.use_case.execute()

        assert fx.use_case.execute() is False
        assert len(fx.sender.sent) == 1

    def test_each_attempt_is_signed_with_a_fresh_timestamp_but_the_same_body_and_id(self) -> None:
        fx = Fixture(DeliveryResult.failed("http_503", 503), OK)
        fx.use_case.execute()
        fx.now = NOW + timedelta(minutes=4)

        fx.use_case.execute()

        (first, second) = fx.sender.sent
        assert (first[0], first[1]) == (second[0], second[1])
        assert first[2] != second[2]
        assert WebhookSigner([SECRET]).verify(second[2], BODY, now=int(fx.now.timestamp()))


class TestRetries:
    def test_a_failure_keeps_the_event_pending_and_waits_exponentially(self) -> None:
        fx = Fixture(DeliveryResult.failed("http_500", 500), DeliveryResult.failed("timeout"))

        fx.use_case.execute()
        assert fx.stored().next_attempt_at == NOW + timedelta(seconds=10)
        assert fx.use_case.execute() is False  # pas encore échu
        fx.now = NOW + timedelta(seconds=10)
        fx.use_case.execute()

        assert fx.stored().status is OutboxStatus.PENDING
        assert (fx.stored().attempts, fx.stored().last_error) == (2, "timeout")
        assert fx.stored().next_attempt_at == fx.now + timedelta(seconds=20)

    def test_the_event_becomes_dead_when_the_attempts_are_exhausted(self) -> None:
        fx = Fixture(*[DeliveryResult.failed("connection_error") for _ in range(3)])

        for _ in range(3):
            fx.use_case.execute()
            fx.now += timedelta(minutes=10)

        assert fx.stored().status is OutboxStatus.DEAD
        assert fx.use_case.execute() is False
        assert len(fx.sender.sent) == 3

    def test_a_delivery_after_failures_ends_delivered_with_the_same_id(self) -> None:
        fx = Fixture(DeliveryResult.failed("http_500", 500), OK)
        fx.use_case.execute()
        fx.now += timedelta(minutes=1)

        fx.use_case.execute()

        assert fx.stored().status is OutboxStatus.DELIVERED
        assert fx.stored().attempts == 2
        assert {sent[0] for sent in fx.sender.sent} == {fx.event.id}


class TestBusinessEvents:
    def _summary(self, fx: Fixture) -> list[tuple[str, Outcome, str | None]]:
        return [(e.event, e.outcome, e.reason) for e in fx.logger.events]

    def test_a_delivery_is_logged_as_a_success(self) -> None:
        fx = Fixture(OK)

        fx.use_case.execute()

        assert self._summary(fx) == [(names.WEBHOOK_DELIVERED, Outcome.SUCCESS, None)]
        (event,) = fx.logger.events
        assert (event.resource_type, event.resource_id) == ("webhook_event", str(fx.event.id))
        assert event.attributes == {
            "event_type": "payment.succeeded",
            "payment_intent_id": str(fx.event.intent_id),
            "attempt": 1,
            "status_code": 200,
        }

    def test_a_failed_attempt_is_an_error_with_the_next_try(self) -> None:
        fx = Fixture(DeliveryResult.failed("http_503", 503))

        fx.use_case.execute()

        assert self._summary(fx) == [(names.WEBHOOK_DELIVERY_FAILED, Outcome.ERROR, "http_503")]
        (event,) = fx.logger.events
        assert event.attributes["attempt"] == 1
        assert event.attributes["status_code"] == 503
        assert event.attributes["retry_in_seconds"] == 10

    def test_a_connection_failure_has_no_status_code(self) -> None:
        fx = Fixture(DeliveryResult.failed("connection_error"))

        fx.use_case.execute()

        (event,) = fx.logger.events
        assert event.reason == "connection_error"
        assert event.attributes["status_code"] is None

    def test_the_last_failure_writes_an_error_for_the_dead_event(self) -> None:
        fx = Fixture(*[DeliveryResult.failed("timeout") for _ in range(3)])
        for _ in range(3):
            fx.use_case.execute()
            fx.now += timedelta(minutes=10)

        assert self._summary(fx)[-1] == (
            names.WEBHOOK_EVENT_DEAD,
            Outcome.ERROR,
            "max_attempts_reached",
        )
        dead = fx.logger.events[-1]
        assert dead.attributes["attempts"] == 3
        assert dead.attributes["last_error"] == "timeout"

    def test_no_secret_signature_or_body_is_ever_logged(self) -> None:
        fx = Fixture(DeliveryResult.failed("http_500", 500), OK)
        fx.use_case.execute()
        fx.now += timedelta(minutes=1)
        fx.use_case.execute()

        logged = repr(fx.logger.events)
        assert SECRET not in logged
        assert "v1=" not in logged
        assert BODY not in logged
