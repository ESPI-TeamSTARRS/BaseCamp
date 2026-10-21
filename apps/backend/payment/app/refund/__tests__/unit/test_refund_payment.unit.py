from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount
from app.refund.application import refund_event_names as names
from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.refund.domain.entities.refund import Refund
from app.refund.domain.exceptions.intent_not_refundable_error import IntentNotRefundableError
from app.refund.domain.exceptions.refund_exceeds_captured_error import RefundExceedsCapturedError
from app.refund.domain.exceptions.refund_key_reused_error import RefundKeyReusedError
from app.refund.domain.interfaces.refund_session import RefundSession
from app.refund.domain.interfaces.refund_unit_of_work import RefundUnitOfWork
from app.webhook.application import webhook_event_names as webhook_names
from app.webhook.domain.entities.outbox_event import OutboxEvent
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.domain.enums.webhook_event_type import WebhookEventType
from app.webhook.domain.services.refund_event_factory import RefundEventFactory

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


class InMemoryStore:
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.refunds: dict[tuple[str, str], Refund] = {}
        self.ledger: list[LedgerTransaction] = []
        self.outbox: list[OutboxEvent] = []


class InMemorySession(RefundSession):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        return self._store.intents.get(intent_id)

    def find_refund(self, caller: str, key: str) -> Refund | None:
        return self._store.refunds.get((caller, key))

    def save(
        self,
        intent: PaymentIntent,
        refund: Refund,
        ledger: LedgerTransaction,
        outbox_event: OutboxEvent,
    ) -> None:
        self._store.intents[intent.id] = intent
        self._store.refunds[(refund.caller, refund.key)] = refund
        self._store.ledger.append(ledger)
        self._store.outbox.append(outbox_event)


class InMemoryUnitOfWork(RefundUnitOfWork):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    @contextmanager
    def begin(self) -> Iterator[RefundSession]:
        yield InMemorySession(self._store)


class Fixture:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.logger = InMemoryBusinessEventLogger()
        self.use_case = RefundPaymentUseCase(
            InMemoryUnitOfWork(self.store), lambda: NOW, self.logger, RefundEventFactory(uuid4)
        )
        created = PaymentIntent.create(
            "CMD-1", Amount(10000), Currency.EUR, NOW - timedelta(minutes=5), timedelta(minutes=30)
        )
        self.intent = created.succeed()
        self.store.intents[self.intent.id] = self.intent

    def with_status(self, status: IntentStatus) -> None:
        self.intent = replace(self.intent, status=status)
        self.store.intents[self.intent.id] = self.intent

    def stored_intent(self) -> PaymentIntent:
        return self.store.intents[self.intent.id]

    def command(self, **overrides: object) -> RefundPaymentCommand:
        values: dict[str, object] = {
            "caller": "shop",
            "idempotency_key": "refund-0001",
            "intent_id": str(self.intent.id),
            "amount": 4000,
        }
        values.update(overrides)
        return RefundPaymentCommand(**values)  # type: ignore[arg-type]


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


class TestSuccessfulRefund:
    def test_a_refund_is_created_and_the_intent_carries_the_refunded_amount(
        self, fx: Fixture
    ) -> None:
        view = fx.use_case.execute(fx.command())

        assert (view.amount, view.amount_refunded) == (4000, 4000)
        assert (view.payment_intent_id, view.currency, view.status) == (
            str(fx.intent.id),
            "EUR",
            "succeeded",
        )
        assert fx.stored_intent().refunded_amount == 4000
        assert fx.stored_intent().status is IntentStatus.SUCCEEDED
        (stored,) = fx.store.refunds.values()
        assert str(stored.id) == view.id

    def test_two_inverse_ledger_entries_are_written_with_the_refund(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        (transaction,) = fx.store.ledger
        debit, credit = transaction.entries
        assert (debit.account, debit.direction) == (LedgerAccount.MARCHAND, EntryDirection.DEBIT)
        assert (credit.account, credit.direction) == (
            LedgerAccount.REMBOURSEMENTS,
            EntryDirection.CREDIT,
        )
        assert debit.amount.cents == credit.amount.cents == 4000

    def test_the_whole_remaining_amount_can_be_refunded_in_two_steps(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        view = fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=6000))

        assert view.amount_refunded == 10000
        assert fx.stored_intent().refunded_amount == 10000
        assert len(fx.store.ledger) == 2

    def test_the_whole_captured_amount_can_be_refunded_at_once(self, fx: Fixture) -> None:
        view = fx.use_case.execute(fx.command(amount=10000))

        assert view.amount_refunded == 10000


class TestAmountCeiling:
    def test_a_refund_above_what_remains_is_a_conflict_and_writes_nothing(
        self, fx: Fixture
    ) -> None:
        fx.use_case.execute(fx.command())

        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=6001))

        assert fx.stored_intent().refunded_amount == 4000
        assert len(fx.store.ledger) == 1
        assert len(fx.store.outbox) == 1
        assert len(fx.store.refunds) == 1

    def test_a_refund_above_the_captured_amount_is_a_conflict(self, fx: Fixture) -> None:
        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(amount=10001))

    def test_nothing_more_can_be_refunded_once_fully_refunded(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command(amount=10000))

        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=1))


class TestIdempotency:
    def test_replaying_the_same_key_returns_the_same_refund_with_a_single_write(
        self, fx: Fixture
    ) -> None:
        first = fx.use_case.execute(fx.command())

        second = fx.use_case.execute(fx.command())

        assert second == first
        assert len(fx.store.ledger) == 1
        assert len(fx.store.outbox) == 1
        assert fx.stored_intent().refunded_amount == 4000

    def test_a_replay_still_returns_the_original_cumulated_amount_after_other_refunds(
        self, fx: Fixture
    ) -> None:
        first = fx.use_case.execute(fx.command())
        fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=1000))

        assert fx.use_case.execute(fx.command()) == first

    def test_a_replay_is_served_even_when_the_intent_is_now_fully_refunded(
        self, fx: Fixture
    ) -> None:
        first = fx.use_case.execute(fx.command())
        fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=6000))

        assert fx.use_case.execute(fx.command()) == first

    def test_the_same_key_with_another_amount_is_refused(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        with pytest.raises(RefundKeyReusedError):
            fx.use_case.execute(fx.command(amount=1000))

        assert fx.stored_intent().refunded_amount == 4000

    def test_the_same_key_on_another_intent_is_refused(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())
        other = replace(fx.intent, id=uuid4(), order_reference="CMD-2", refunded_amount=0)
        fx.store.intents[other.id] = other

        with pytest.raises(RefundKeyReusedError):
            fx.use_case.execute(fx.command(intent_id=str(other.id)))

    def test_keys_are_scoped_per_caller(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        fx.use_case.execute(fx.command(caller="other"))

        assert fx.stored_intent().refunded_amount == 8000


class TestRefusedRefund:
    @pytest.mark.parametrize(
        "status",
        [
            IntentStatus.REQUIRES_CONFIRMATION,
            IntentStatus.FAILED,
            IntentStatus.CANCELED,
            IntentStatus.EXPIRED,
        ],
    )
    def test_an_intent_that_did_not_succeed_is_a_conflict(
        self, fx: Fixture, status: IntentStatus
    ) -> None:
        fx.with_status(status)

        with pytest.raises(IntentNotRefundableError):
            fx.use_case.execute(fx.command())

        assert fx.store.ledger == []
        assert fx.store.outbox == []

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_an_unknown_or_malformed_intent_is_not_found(self, fx: Fixture, intent_id: str) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.execute(fx.command(intent_id=intent_id))


class TestOutboxEvent:
    def test_a_refund_queues_a_refund_succeeded_event_in_the_same_save(self, fx: Fixture) -> None:
        view = fx.use_case.execute(fx.command())

        (queued,) = fx.store.outbox
        assert queued.event_type is WebhookEventType.REFUND_SUCCEEDED
        assert queued.status is OutboxStatus.PENDING
        assert queued.intent_id == fx.intent.id
        assert f'"refund_id":"{view.id}"' in queued.body
        assert '"amount":4000' in queued.body
        assert '"amount_refunded":4000' in queued.body

    def test_a_replay_or_a_refusal_queues_nothing_more(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())
        fx.use_case.execute(fx.command())
        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=6001))

        assert len(fx.store.outbox) == 1


class TestBusinessEvents:
    def _summary(self, fx: Fixture) -> list[tuple[str, Outcome, str | None]]:
        return [(e.event, e.outcome, e.reason) for e in fx.logger.events]

    def test_a_success_logs_the_refund_the_ledger_write_then_the_queued_event(
        self, fx: Fixture
    ) -> None:
        view = fx.use_case.execute(fx.command())

        assert self._summary(fx) == [
            (names.REFUND_SUCCEEDED, Outcome.SUCCESS, None),
            (names.LEDGER_ENTRIES_WRITTEN, Outcome.SUCCESS, None),
            (webhook_names.WEBHOOK_EVENT_QUEUED, Outcome.SUCCESS, None),
        ]
        refunded, ledger, _queued = fx.logger.events
        assert (refunded.resource_type, refunded.resource_id) == ("refund", view.id)
        assert (refunded.actor_type, refunded.actor_id) == ("service", "shop")
        assert refunded.attributes == {
            "payment_intent_id": str(fx.intent.id),
            "order_reference": "CMD-1",
            "amount_cents": 4000,
            "amount_refunded_cents": 4000,
            "currency": "EUR",
        }
        assert (ledger.resource_type, ledger.resource_id) == ("payment_intent", str(fx.intent.id))
        assert ledger.attributes == {
            "transaction_id": str(fx.store.ledger[0].id),
            "entry_count": 2,
            "amount_cents": 4000,
        }

    def test_a_replay_logs_nothing_new(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())
        fx.logger.events.clear()

        fx.use_case.execute(fx.command())

        assert fx.logger.events == []

    def test_an_excess_is_a_denied_event_with_the_requested_and_remaining_amounts(
        self, fx: Fixture
    ) -> None:
        fx.use_case.execute(fx.command())
        fx.logger.events.clear()

        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=6001))

        (event,) = fx.logger.events
        assert (event.event, event.outcome, event.reason) == (
            names.REFUND_REJECTED,
            Outcome.DENIED,
            "amount_exceeds_refundable",
        )
        assert (event.resource_type, event.resource_id) == ("payment_intent", str(fx.intent.id))
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert event.attributes == {
            "order_reference": "CMD-1",
            "currency": "EUR",
            "requested_cents": 6001,
            "refundable_cents": 6000,
        }

    def test_an_intent_that_did_not_succeed_is_rejected_with_its_status(self, fx: Fixture) -> None:
        fx.with_status(IntentStatus.FAILED)

        with pytest.raises(IntentNotRefundableError):
            fx.use_case.execute(fx.command())

        assert self._summary(fx) == [(names.REFUND_REJECTED, Outcome.DENIED, "status_failed")]

    def test_a_reused_key_is_rejected(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())
        fx.logger.events.clear()

        with pytest.raises(RefundKeyReusedError):
            fx.use_case.execute(fx.command(amount=1000))

        assert self._summary(fx) == [
            (names.REFUND_REJECTED, Outcome.DENIED, "idempotency_key_reused")
        ]

    def test_an_unknown_intent_is_rejected_without_echoing_the_received_id(
        self, fx: Fixture
    ) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.execute(fx.command(intent_id="4242424242424242"))

        (event,) = fx.logger.events
        assert (event.event, event.reason) == (names.REFUND_REJECTED, "intent_not_found")
        assert event.resource_id is None
        assert "4242" not in repr(event)

    def test_the_idempotency_key_never_appears_in_an_event(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())
        with pytest.raises(RefundExceedsCapturedError):
            fx.use_case.execute(fx.command(idempotency_key="refund-0002", amount=9999))

        assert "refund-000" not in repr(fx.logger.events)

    def test_the_queued_event_is_logged_without_the_body(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        queued = fx.store.outbox[0]
        (event,) = [e for e in fx.logger.events if e.event == webhook_names.WEBHOOK_EVENT_QUEUED]
        assert (event.resource_type, event.resource_id) == ("webhook_event", str(queued.id))
        assert event.attributes == {
            "event_type": "refund.succeeded",
            "payment_intent_id": str(fx.intent.id),
        }
        assert queued.body not in repr(event)
