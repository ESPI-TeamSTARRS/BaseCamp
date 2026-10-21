import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.value_objects.amount import Amount
from app.refund.__tests__.support import InMemoryStore, InMemoryUnitOfWork
from app.refund.application.refund_expired_order import RefundExpiredOrderUseCase
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.refund.domain.exceptions.refund_exceeds_captured_error import RefundExceedsCapturedError
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.refund_event_factory import RefundEventFactory

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
CAPTURED = 10000


class Fixture:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.logger = InMemoryBusinessEventLogger()
        refund = RefundPaymentUseCase(
            InMemoryUnitOfWork(self.store), lambda: NOW, self.logger, RefundEventFactory(uuid4)
        )
        self.use_case = RefundExpiredOrderUseCase(refund)
        created = PaymentIntent.create(
            "BC-ABCDEFGHJK",
            Amount(CAPTURED),
            Currency.EUR,
            NOW - timedelta(minutes=5),
            timedelta(minutes=30),
        )
        self.intent = created.succeed()
        self.store.intents[self.intent.id] = self.intent

    def late_payment(self, intent_id: object = None, amount: int = CAPTURED) -> OutboxEvent:
        body = json.dumps(
            {
                "id": "e",
                "type": "payment.succeeded",
                "data": {"order_reference": "BC-ABCDEFGHJK", "amount": amount, "currency": "EUR"},
            },
            separators=(",", ":"),
        )
        return OutboxEvent.pending(
            uuid4(),
            WebhookEventType.PAYMENT_SUCCEEDED,
            intent_id or self.intent.id,  # type: ignore[arg-type]
            body,
            NOW,
        )


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


class TestRefundExpiredOrder:
    def test_the_whole_captured_amount_is_refunded_by_the_worker_with_an_event_derived_key(
        self, fx: Fixture
    ) -> None:
        event = fx.late_payment()

        fx.use_case.refund_in_full(event)

        stored = fx.store.intents[fx.intent.id]
        assert (stored.refunded_amount, stored.status) == (CAPTURED, IntentStatus.SUCCEEDED)
        ((caller, key),) = fx.store.refunds
        assert (caller, key) == ("payment-worker", f"auto-refund-{event.id}")
        assert len(fx.store.ledger) == 1
        assert [e.event_type for e in fx.store.outbox] == [WebhookEventType.REFUND_SUCCEEDED]

    def test_the_same_event_replayed_never_refunds_twice(self, fx: Fixture) -> None:
        event = fx.late_payment()

        fx.use_case.refund_in_full(event)
        fx.use_case.refund_in_full(event)

        assert fx.store.intents[fx.intent.id].refunded_amount == CAPTURED
        assert (len(fx.store.refunds), len(fx.store.ledger), len(fx.store.outbox)) == (1, 1, 1)

    def test_an_unknown_intent_is_an_error_so_the_attempt_is_retried_and_alerts(
        self, fx: Fixture
    ) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.refund_in_full(fx.late_payment(intent_id=uuid4()))

        assert fx.store.refunds == {}

    def test_an_intent_already_refunded_by_someone_else_is_an_error_never_a_second_refund(
        self, fx: Fixture
    ) -> None:
        fx.store.intents[fx.intent.id] = fx.intent.refund(Amount(CAPTURED))

        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.refund_in_full(fx.late_payment())

        assert fx.store.refunds == {}

    @pytest.mark.parametrize(
        "body", ["pas du json", "[]", '{"data":{}}', '{"data":{"amount":"1"}}']
    )
    def test_an_unreadable_event_body_is_refused_without_refunding(
        self, fx: Fixture, body: str
    ) -> None:
        event = OutboxEvent.pending(
            uuid4(), WebhookEventType.PAYMENT_SUCCEEDED, fx.intent.id, body, NOW
        )

        with pytest.raises(ValueError, match="amount"):
            fx.use_case.refund_in_full(event)

        assert fx.store.refunds == {}
