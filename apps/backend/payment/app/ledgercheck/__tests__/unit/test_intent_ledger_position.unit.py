from uuid import uuid4

import pytest

from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.__tests__.support import position
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind


class TestExpectedBalance:
    def test_a_succeeded_intent_expects_the_captured_amount(self) -> None:
        assert position(amount=10000).expected_balance_cents == 10000

    def test_a_refund_lowers_the_expected_balance(self) -> None:
        assert position(amount=10000, refunded=4000).expected_balance_cents == 6000

    def test_a_fully_refunded_intent_expects_zero(self) -> None:
        assert position(amount=10000, refunded=10000).expected_balance_cents == 0

    @pytest.mark.parametrize(
        "status",
        [
            IntentStatus.REQUIRES_CONFIRMATION,
            IntentStatus.FAILED,
            IntentStatus.CANCELED,
            IntentStatus.EXPIRED,
        ],
    )
    def test_an_intent_that_was_never_paid_expects_zero(self, status: IntentStatus) -> None:
        assert position(status=status).expected_balance_cents == 0


class TestDiscrepancy:
    def test_a_healthy_position_has_no_discrepancy(self) -> None:
        assert position(amount=10000, refunded=4000).discrepancy() is None

    def test_an_altered_line_reports_expected_and_observed_amounts(self) -> None:
        intent_id = uuid4()

        found = position(amount=10000, balance=9000, intent_id=intent_id).discrepancy()

        assert found is not None
        assert (found.kind, found.resource_id) == (DiscrepancyKind.INTENT_BALANCE, intent_id)
        assert (found.expected_cents, found.observed_cents) == (10000, 9000)

    def test_a_line_on_an_unpaid_intent_is_an_orphan_with_zero_expected(self) -> None:
        found = position(status=IntentStatus.EXPIRED, balance=2500).discrepancy()

        assert found is not None
        assert (found.expected_cents, found.observed_cents) == (0, 2500)

    def test_a_missing_line_on_a_paid_intent_is_reported(self) -> None:
        found = position(amount=10000, balance=0).discrepancy()

        assert found is not None
        assert (found.expected_cents, found.observed_cents) == (10000, 0)
