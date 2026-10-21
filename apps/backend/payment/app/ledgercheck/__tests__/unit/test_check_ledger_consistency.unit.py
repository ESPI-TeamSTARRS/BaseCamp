from uuid import UUID

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.__tests__.support import StubLedgerReader, balanced, position
from app.ledgercheck.application import ledger_check_event_names as names
from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase
from app.ledgercheck.application.check_ledger_consistency import CheckLedgerConsistencyUseCase
from app.ledgercheck.application.exceptions.ledger_check_unavailable_error import (
    LedgerCheckUnavailableError,
)
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance

TICKS = iter(range(0, 10_000, 3))


def _timer() -> float:
    return next(TICKS) / 1000


def _use_case(
    reader: StubLedgerReader, events: InMemoryBusinessEventLogger, max_logged: int = 100
) -> CheckLedgerConsistencyUseCase:
    return CheckLedgerConsistencyUseCase(AuditLedgerUseCase(reader), events, _timer, max_logged)


HEALTHY = LedgerSnapshot((position(10000, 4000), position(2500)), (balanced(), balanced(4000)))


class TestHealthyLedger:
    def test_it_returns_the_consistent_result_and_logs_one_success_summary(self) -> None:
        events = InMemoryBusinessEventLogger()

        result = _use_case(StubLedgerReader(HEALTHY), events).execute()

        assert result.is_consistent
        (summary,) = events.events
        assert (summary.event, summary.outcome, summary.reason) == (
            names.LEDGER_CHECK_COMPLETED,
            Outcome.SUCCESS,
            None,
        )
        assert summary.attributes == {
            "intents_checked": 2,
            "transactions_checked": 2,
            "entry_count": 4,
            "debit_cents": 14000,
            "credit_cents": 14000,
        }
        assert summary.duration_ms == 3


class TestInconsistentLedger:
    def test_each_discrepancy_is_an_error_event_with_amounts_and_the_summary_is_an_error(
        self,
    ) -> None:
        events = InMemoryBusinessEventLogger()
        altered = position(10000, balance=9000, intent_id=UUID(int=1))
        orphan = position(status=IntentStatus.EXPIRED, balance=2500, intent_id=UUID(int=2))
        broken = TransactionBalance(UUID(int=3), 1, 5000, 0)
        reader = StubLedgerReader(LedgerSnapshot((altered, orphan), (broken,)))

        result = _use_case(reader, events).execute()

        assert not result.is_consistent
        details, summary = events.events[:-1], events.events[-1]
        assert [(e.event, e.outcome, e.reason) for e in details] == [
            (names.LEDGER_INCONSISTENCY_DETECTED, Outcome.ERROR, "intent_balance_mismatch"),
            (names.LEDGER_INCONSISTENCY_DETECTED, Outcome.ERROR, "intent_balance_mismatch"),
            (names.LEDGER_INCONSISTENCY_DETECTED, Outcome.ERROR, "transaction_unbalanced"),
        ]
        assert [(e.resource_type, e.resource_id) for e in details] == [
            ("payment_intent", str(UUID(int=1))),
            ("payment_intent", str(UUID(int=2))),
            ("ledger_transaction", str(UUID(int=3))),
        ]
        assert [dict(e.attributes) for e in details] == [
            {"expected_cents": 10000, "observed_cents": 9000},
            {"expected_cents": 0, "observed_cents": 2500},
            {"expected_cents": 5000, "observed_cents": 0},
        ]
        assert (summary.event, summary.outcome, summary.reason) == (
            names.LEDGER_CHECK_COMPLETED,
            Outcome.ERROR,
            "ledger_inconsistent",
        )
        assert summary.attributes["discrepancy_count"] == 3

    def test_detail_events_are_capped_but_the_summary_keeps_the_total(self) -> None:
        events = InMemoryBusinessEventLogger()
        broken = tuple(position(10000, balance=1) for _ in range(7))

        _use_case(StubLedgerReader(LedgerSnapshot(broken, ())), events, max_logged=5).execute()

        details = [e for e in events.events if e.event == names.LEDGER_INCONSISTENCY_DETECTED]
        summary = events.events[-1]
        assert len(details) == 5
        assert summary.attributes["discrepancy_count"] == 7

    def test_no_event_carries_anything_but_identifiers_and_amounts(self) -> None:
        events = InMemoryBusinessEventLogger()
        reader = StubLedgerReader(LedgerSnapshot((position(10000, balance=1),), ()))

        _use_case(reader, events).execute()

        allowed = {
            "expected_cents",
            "observed_cents",
            "discrepancy_count",
            "intents_checked",
            "transactions_checked",
            "entry_count",
            "debit_cents",
            "credit_cents",
        }
        for event in events.events:
            assert set(event.attributes) <= allowed
            assert event.actor_id is None
            assert event.client_ip is None


class TestReadFailure:
    def test_it_logs_a_failure_event_and_propagates(self) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(LedgerCheckUnavailableError):
            _use_case(StubLedgerReader(fail=True), events).execute()

        (failed,) = events.events
        assert (failed.event, failed.outcome, failed.reason) == (
            names.LEDGER_CHECK_FAILED,
            Outcome.ERROR,
            "database_error",
        )
