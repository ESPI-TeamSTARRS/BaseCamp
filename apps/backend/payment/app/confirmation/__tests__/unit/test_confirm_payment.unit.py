from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.confirmation.application.confirm_payment import ConfirmPaymentUseCase
from app.confirmation.domain.entities.confirmation_record import ConfirmationRecord
from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.exceptions.confirmation_key_reused_error import (
    ConfirmationKeyReusedError,
)
from app.confirmation.domain.exceptions.intent_not_confirmable_error import (
    IntentNotConfirmableError,
)
from app.confirmation.domain.interfaces.confirmation_session import ConfirmationSession
from app.confirmation.domain.interfaces.confirmation_unit_of_work import ConfirmationUnitOfWork
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.intent.domain.enums.currency import Currency
from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.domain.exceptions.payment_intent_not_found_error import PaymentIntentNotFoundError
from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


class InMemoryStore:
    def __init__(self) -> None:
        self.intents: dict[UUID, PaymentIntent] = {}
        self.records: dict[tuple[str, str], ConfirmationRecord] = {}
        self.ledger: list[LedgerTransaction] = []


class InMemorySession(ConfirmationSession):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def lock_intent(self, intent_id: UUID) -> PaymentIntent | None:
        return self._store.intents.get(intent_id)

    def find_record(self, caller: str, key: str) -> ConfirmationRecord | None:
        return self._store.records.get((caller, key))

    def save(
        self, intent: PaymentIntent, record: ConfirmationRecord, ledger: LedgerTransaction | None
    ) -> None:
        self._store.intents[intent.id] = intent
        self._store.records[(record.caller, record.key)] = record
        if ledger:
            self._store.ledger.append(ledger)


class InMemoryUnitOfWork(ConfirmationUnitOfWork):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    @contextmanager
    def begin(self) -> Iterator[ConfirmationSession]:
        yield InMemorySession(self._store)


class FakeProvider(PaymentProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[PaymentMethod, int]] = []

    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome:
        self.calls.append((method, amount.cents))
        return {
            PaymentMethod.SUCCESS: ProviderOutcome.APPROVED,
            PaymentMethod.DECLINED: ProviderOutcome.DECLINED,
            PaymentMethod.TIMEOUT: ProviderOutcome.TIMED_OUT,
        }[method]


class Fixture:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.provider = FakeProvider()
        self.use_case = ConfirmPaymentUseCase(
            InMemoryUnitOfWork(self.store), self.provider, lambda: NOW
        )
        self.intent = PaymentIntent.create(
            "CMD-1", Amount(4990), Currency.EUR, NOW - timedelta(minutes=1), timedelta(minutes=30)
        )
        self.store.intents[self.intent.id] = self.intent

    def with_status(self, status: IntentStatus) -> None:
        self.intent = replace(self.intent, status=status)
        self.store.intents[self.intent.id] = self.intent

    def command(self, **overrides: object) -> ConfirmPaymentCommand:
        values: dict[str, object] = {
            "caller": "shop",
            "idempotency_key": "key-0001",
            "intent_id": str(self.intent.id),
            "payment_method": "pm_test_success",
        }
        values.update(overrides)
        return ConfirmPaymentCommand(**values)  # type: ignore[arg-type]


@pytest.fixture
def fx() -> Fixture:
    return Fixture()


class TestSuccessfulConfirmation:
    def test_the_intent_succeeds_and_two_balanced_ledger_entries_are_written(
        self, fx: Fixture
    ) -> None:
        view = fx.use_case.execute(fx.command())

        assert view.status == "succeeded"
        assert fx.store.intents[fx.intent.id].status is IntentStatus.SUCCEEDED
        (transaction,) = fx.store.ledger
        debit, credit = transaction.entries
        assert (debit.account, debit.direction) == (
            LedgerAccount.CLIENT_ATTENTE,
            EntryDirection.DEBIT,
        )
        assert (credit.account, credit.direction) == (LedgerAccount.MARCHAND, EntryDirection.CREDIT)
        assert debit.amount.cents == credit.amount.cents == 4990

    def test_the_amount_given_to_the_provider_is_the_one_stored_on_the_server(
        self, fx: Fixture
    ) -> None:
        fx.use_case.execute(fx.command())

        assert fx.provider.calls == [(PaymentMethod.SUCCESS, 4990)]


class TestFailedConfirmation:
    @pytest.mark.parametrize("method", ["pm_test_declined", "pm_test_timeout"])
    def test_a_decline_or_a_timeout_fails_the_intent_without_any_ledger_entry(
        self, fx: Fixture, method: str
    ) -> None:
        view = fx.use_case.execute(fx.command(payment_method=method))

        assert view.status == "failed"
        assert fx.store.ledger == []
        assert ("shop", "key-0001") in fx.store.records


class TestIdempotency:
    def test_replaying_the_same_key_returns_the_same_result_with_a_single_write(
        self, fx: Fixture
    ) -> None:
        first = fx.use_case.execute(fx.command())

        second = fx.use_case.execute(fx.command())

        assert second == first
        assert len(fx.store.ledger) == 1
        assert len(fx.provider.calls) == 1

    def test_replaying_a_failed_confirmation_returns_the_failure(self, fx: Fixture) -> None:
        first = fx.use_case.execute(fx.command(payment_method="pm_test_declined"))

        second = fx.use_case.execute(fx.command(payment_method="pm_test_declined"))

        assert second == first
        assert second.status == "failed"

    def test_another_key_on_an_already_succeeded_intent_is_a_conflict(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        with pytest.raises(IntentNotConfirmableError):
            fx.use_case.execute(fx.command(idempotency_key="key-0002"))

        assert len(fx.store.ledger) == 1

    def test_the_same_key_with_another_method_is_refused(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        with pytest.raises(ConfirmationKeyReusedError):
            fx.use_case.execute(fx.command(payment_method="pm_test_declined"))

    def test_keys_are_scoped_per_caller(self, fx: Fixture) -> None:
        fx.use_case.execute(fx.command())

        with pytest.raises(IntentNotConfirmableError):
            fx.use_case.execute(fx.command(caller="other"))


class TestRefusedConfirmation:
    def test_an_expired_intent_is_a_conflict_and_the_provider_is_not_called(
        self, fx: Fixture
    ) -> None:
        fx.store.intents[fx.intent.id] = replace(fx.intent, expires_at=NOW)

        with pytest.raises(IntentNotConfirmableError):
            fx.use_case.execute(fx.command())

        assert fx.provider.calls == []
        assert fx.store.ledger == []

    @pytest.mark.parametrize(
        "status", [IntentStatus.CANCELED, IntentStatus.EXPIRED, IntentStatus.FAILED]
    )
    def test_a_canceled_expired_or_failed_intent_is_a_conflict(
        self, fx: Fixture, status: IntentStatus
    ) -> None:
        fx.with_status(status)

        with pytest.raises(IntentNotConfirmableError):
            fx.use_case.execute(fx.command())

        assert fx.provider.calls == []

    @pytest.mark.parametrize("intent_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_an_unknown_or_malformed_intent_is_not_found(self, fx: Fixture, intent_id: str) -> None:
        with pytest.raises(PaymentIntentNotFoundError):
            fx.use_case.execute(fx.command(intent_id=intent_id))
