from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.intent.domain.value_objects.amount import Amount
from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount
from app.ledger.domain.exceptions.unbalanced_transaction_error import UnbalancedTransactionError

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


class TestPaymentReceived:
    def test_writes_a_debit_on_the_waiting_account_and_a_credit_on_the_merchant(self) -> None:
        intent_id = uuid4()

        transaction = LedgerTransaction.payment_received(intent_id, Amount(4990), NOW)

        debit, credit = transaction.entries
        assert (debit.account, debit.direction) == (
            LedgerAccount.CLIENT_ATTENTE,
            EntryDirection.DEBIT,
        )
        assert (credit.account, credit.direction) == (LedgerAccount.MARCHAND, EntryDirection.CREDIT)
        assert debit.amount.cents == credit.amount.cents == 4990
        assert {entry.intent_id for entry in transaction.entries} == {intent_id}
        assert {entry.created_at for entry in transaction.entries} == {NOW}

    def test_both_entries_share_the_transaction_identifier(self) -> None:
        transaction = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)

        assert {entry.transaction_id for entry in transaction.entries} == {transaction.id}

    def test_each_transaction_has_its_own_identifier(self) -> None:
        first = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)
        second = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)

        assert first.id != second.id


class TestBalance:
    def test_a_transaction_whose_debits_differ_from_credits_is_refused(self) -> None:
        valid = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)
        skewed = replace(valid.entries[1], amount=Amount(99))

        with pytest.raises(UnbalancedTransactionError):
            LedgerTransaction(valid.id, (valid.entries[0], skewed))

    def test_a_transaction_needs_both_sides(self) -> None:
        valid = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)

        with pytest.raises(UnbalancedTransactionError):
            LedgerTransaction(valid.id, (valid.entries[0],))

    def test_entries_of_another_transaction_are_refused(self) -> None:
        valid = LedgerTransaction.payment_received(uuid4(), Amount(100), NOW)

        with pytest.raises(UnbalancedTransactionError):
            LedgerTransaction(uuid4(), valid.entries)
