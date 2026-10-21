import time
from uuid import UUID

from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.__tests__.support import balanced, position
from app.ledgercheck.domain.entities.ledger_check_result import LedgerCheckResult
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind
from app.ledgercheck.domain.services.ledger_auditor import LedgerAuditor


def _audit(snapshot: LedgerSnapshot) -> LedgerCheckResult:
    return LedgerAuditor().audit(snapshot)


class TestHealthyLedger:
    def test_an_empty_ledger_is_consistent(self) -> None:
        result = _audit(LedgerSnapshot((), ()))

        assert result.is_consistent
        assert (result.intents_checked, result.transactions_checked, result.entry_count) == (
            0,
            0,
            0,
        )

    def test_totals_count_what_was_checked(self) -> None:
        snapshot = LedgerSnapshot(
            (position(10000, 4000), position(2500), position(status=IntentStatus.EXPIRED)),
            (balanced(10000), balanced(4000), balanced(2500)),
        )

        result = _audit(snapshot)

        assert result.is_consistent
        assert result.discrepancies == ()
        assert (result.intents_checked, result.transactions_checked) == (3, 3)
        assert result.entry_count == 6
        assert (result.debit_cents, result.credit_cents) == (16500, 16500)


class TestAlteredLedger:
    def test_every_discrepancy_is_listed_with_expected_and_observed(self) -> None:
        altered = position(10000, balance=9000)
        orphan = position(status=IntentStatus.EXPIRED, balance=2500)
        broken = TransactionBalance(UUID(int=7), 1, 5000, 0)
        snapshot = LedgerSnapshot((position(), altered, orphan), (balanced(), broken))

        result = _audit(snapshot)

        assert not result.is_consistent
        assert result.discrepancy_count == 3
        by_id = {d.resource_id: d for d in result.discrepancies}
        assert (
            by_id[altered.intent_id].expected_cents,
            by_id[altered.intent_id].observed_cents,
        ) == (
            10000,
            9000,
        )
        assert by_id[orphan.intent_id].expected_cents == 0
        assert by_id[broken.transaction_id].kind is DiscrepancyKind.TRANSACTION_UNBALANCED

    def test_unbalanced_global_totals_alone_make_the_ledger_inconsistent(self) -> None:
        result = _audit(LedgerSnapshot((), (TransactionBalance(UUID(int=1), 1, 100, 0),)))

        assert (result.debit_cents, result.credit_cents) == (100, 0)
        assert not result.is_consistent

    def test_discrepancies_come_in_a_stable_order(self) -> None:
        snapshot = LedgerSnapshot(
            (
                position(balance=1, intent_id=UUID(int=9)),
                position(balance=1, intent_id=UUID(int=2)),
            ),
            (TransactionBalance(UUID(int=5), 1, 10, 0),),
        )

        first, second = _audit(snapshot), _audit(snapshot)

        assert first.discrepancies == second.discrepancies
        assert [d.resource_id.int for d in first.discrepancies] == [2, 9, 5]


class TestVolume:
    def test_ten_thousand_intents_are_audited_in_memory_well_under_a_second(self) -> None:
        snapshot = LedgerSnapshot(
            tuple(position(10000, 3000 * (n % 2)) for n in range(10_000)),
            tuple(balanced() for _ in range(15_000)),
        )

        started = time.perf_counter()
        result = _audit(snapshot)

        assert result.is_consistent
        assert time.perf_counter() - started < 0.5
