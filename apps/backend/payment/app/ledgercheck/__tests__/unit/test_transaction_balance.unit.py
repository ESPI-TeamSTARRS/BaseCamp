from uuid import uuid4

from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind


class TestTransactionBalance:
    def test_equal_debits_and_credits_are_balanced(self) -> None:
        assert TransactionBalance(uuid4(), 2, 5000, 5000).discrepancy() is None

    def test_unequal_totals_report_debits_as_expected_and_credits_as_observed(self) -> None:
        transaction_id = uuid4()

        found = TransactionBalance(transaction_id, 2, 5000, 4000).discrepancy()

        assert found is not None
        assert (found.kind, found.resource_id) == (
            DiscrepancyKind.TRANSACTION_UNBALANCED,
            transaction_id,
        )
        assert (found.expected_cents, found.observed_cents) == (5000, 4000)
