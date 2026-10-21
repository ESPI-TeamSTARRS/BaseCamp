from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from sqlalchemy import CheckConstraint


class TestLedgerEntryModel:
    def test_amounts_are_integer_cents_with_a_positive_check(self) -> None:
        table = LedgerEntryModel.__table__
        constraints = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}

        assert str(table.c.amount.type) == "BIGINT"
        assert "ck_ledger_entries_amount_positive" in constraints
        assert "ck_ledger_entries_direction" in constraints
