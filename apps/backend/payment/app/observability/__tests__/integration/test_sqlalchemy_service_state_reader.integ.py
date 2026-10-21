from datetime import UTC, datetime, timedelta

import pytest
from app.observability.infrastructure.repositories.sqlalchemy_service_state_reader import (
    SqlAlchemyServiceStateReader,
)
from sqlalchemy import Engine, StaticPool, create_engine, event
from sqlalchemy.exc import OperationalError

from app.intent.infrastructure.models.base import Base
from app.observability.__tests__.integration.seeding import add_entries, add_intent, add_outbox

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
RECENT = NOW - timedelta(hours=1)
OLD = NOW - timedelta(hours=48)
LOOKBACK = timedelta(hours=24)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    return engine


def _read(engine: Engine):  # type: ignore[no-untyped-def]
    state = SqlAlchemyServiceStateReader(engine, LOOKBACK).read(NOW)
    assert state is not None
    return state


class TestEmptyDatabase:
    def test_every_known_status_and_discrepancy_kind_is_reported_as_zero(
        self, engine: Engine
    ) -> None:
        state = _read(engine)

        assert state.intents_by_status == {
            "requires_confirmation": 0,
            "succeeded": 0,
            "failed": 0,
            "canceled": 0,
            "expired": 0,
        }
        assert state.webhook_events_by_status == {"pending": 0, "delivered": 0, "dead": 0}
        assert state.webhook_oldest_pending_age_seconds == 0
        assert (state.captured_amount_cents, state.refunded_amount_cents) == (0, 0)
        assert state.refunded_intents == 0
        assert state.ledger_discrepancies == {
            "unbalanced_transaction": 0,
            "succeeded_without_entries": 0,
            "amount_mismatch": 0,
            "entries_without_success": 0,
        }


class TestIntentsAndPayments:
    def test_intents_are_counted_by_status(self, engine: Engine) -> None:
        for status in ("succeeded", "succeeded", "failed", "requires_confirmation"):
            add_intent(engine, RECENT, status)

        counts = _read(engine).intents_by_status

        assert (counts["succeeded"], counts["failed"], counts["requires_confirmation"]) == (2, 1, 1)

    def test_captured_and_refunded_amounts_come_from_succeeded_intents_only(
        self, engine: Engine
    ) -> None:
        add_intent(engine, RECENT, "succeeded", amount=5000, refunded=2000)
        add_intent(engine, RECENT, "succeeded", amount=3000, refunded=0)
        add_intent(engine, RECENT, "failed", amount=9000)

        state = _read(engine)

        assert state.captured_amount_cents == 8000
        assert state.refunded_amount_cents == 2000
        assert state.refunded_intents == 1


class TestWebhookEvents:
    def test_events_are_counted_by_status_and_the_oldest_pending_one_is_aged(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine, RECENT, "succeeded")
        add_outbox(engine, intent, "pending", NOW - timedelta(seconds=90))
        add_outbox(engine, intent, "pending", NOW - timedelta(seconds=30))
        add_outbox(engine, intent, "dead", RECENT, "payment.failed")
        add_outbox(engine, intent, "delivered", RECENT)

        state = _read(engine)

        assert state.webhook_events_by_status == {"pending": 2, "delivered": 1, "dead": 1}
        assert state.webhook_oldest_pending_age_seconds == 90


class TestLedgerDiscrepancies:
    def test_a_consistent_payment_is_no_discrepancy(self, engine: Engine) -> None:
        intent = add_intent(engine, RECENT, "succeeded", amount=5000)
        add_entries(engine, intent, RECENT, debit=5000, credit=5000)

        assert set(_read(engine).ledger_discrepancies.values()) == {0}

    def test_a_succeeded_intent_without_entries_is_flagged(self, engine: Engine) -> None:
        add_intent(engine, RECENT, "succeeded")

        assert _read(engine).ledger_discrepancies["succeeded_without_entries"] == 1

    def test_entries_that_do_not_match_the_intent_amount_are_flagged(self, engine: Engine) -> None:
        intent = add_intent(engine, RECENT, "succeeded", amount=5000)
        add_entries(engine, intent, RECENT, debit=4000, credit=4000)

        assert _read(engine).ledger_discrepancies["amount_mismatch"] == 1

    def test_an_unbalanced_transaction_is_flagged(self, engine: Engine) -> None:
        intent = add_intent(engine, RECENT, "succeeded", amount=5000)
        add_entries(engine, intent, RECENT, debit=5000, credit=4000)

        assert _read(engine).ledger_discrepancies["unbalanced_transaction"] == 1

    def test_entries_on_an_intent_that_did_not_succeed_are_flagged_once_per_transaction(
        self, engine: Engine
    ) -> None:
        intent = add_intent(engine, RECENT, "failed", amount=5000)
        add_entries(engine, intent, RECENT, debit=5000, credit=5000)

        assert _read(engine).ledger_discrepancies["entries_without_success"] == 1

    def test_intents_older_than_the_lookback_window_are_not_scanned(self, engine: Engine) -> None:
        add_intent(engine, OLD, "succeeded")
        broken = add_intent(engine, OLD, "succeeded", amount=5000)
        add_entries(engine, broken, OLD, debit=5000, credit=1)

        assert set(_read(engine).ledger_discrepancies.values()) == {0}


class TestUnavailableDatabase:
    def test_it_returns_none_instead_of_raising(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")  # aucune table : lecture impossible

        assert SqlAlchemyServiceStateReader(engine, LOOKBACK).read(NOW) is None

    def test_a_connection_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")

        def refuse() -> None:
            raise OperationalError("SELECT 1", {}, Exception("down"))

        monkeypatch.setattr(engine, "connect", refuse)

        assert SqlAlchemyServiceStateReader(engine, LOOKBACK).read(NOW) is None
