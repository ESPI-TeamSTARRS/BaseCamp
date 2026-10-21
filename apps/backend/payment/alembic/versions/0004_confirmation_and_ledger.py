"""Clés d'idempotence de confirmation et grand livre en ajout seul, équilibré par transaction.

Compatible avec la version précédente : nouvelles tables seulement (aucune table existante
modifiée); les déclencheurs et contraintes ne portent que sur ces nouvelles tables.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FORBID_CHANGES = """
CREATE FUNCTION ledger_entries_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries est en ajout seul';
END;
$$
"""

_CHECK_BALANCE = """
CREATE FUNCTION ledger_entries_check_balance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    total_debits bigint;
    total_credits bigint;
BEGIN
    SELECT COALESCE(SUM(amount) FILTER (WHERE direction = 'debit'), 0),
           COALESCE(SUM(amount) FILTER (WHERE direction = 'credit'), 0)
      INTO total_debits, total_credits
      FROM ledger_entries
     WHERE transaction_id = NEW.transaction_id;
    IF total_debits <> total_credits THEN
        RAISE EXCEPTION 'transaction % desequilibree : debits % credits %',
            NEW.transaction_id, total_debits, total_credits;
    END IF;
    RETURN NULL;
END;
$$
"""

_TRIGGERS = (
    """CREATE TRIGGER ledger_entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
       FOR EACH ROW EXECUTE FUNCTION ledger_entries_forbid_change()""",
    """CREATE TRIGGER ledger_entries_no_truncate BEFORE TRUNCATE ON ledger_entries
       FOR EACH STATEMENT EXECUTE FUNCTION ledger_entries_forbid_change()""",
    """CREATE CONSTRAINT TRIGGER ledger_entries_balanced AFTER INSERT ON ledger_entries
       DEFERRABLE INITIALLY DEFERRED
       FOR EACH ROW EXECUTE FUNCTION ledger_entries_check_balance()""",
)


def upgrade() -> None:
    op.create_table(
        "confirmation_keys",
        sa.Column("caller", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("caller", "key"),
    )
    op.create_index("ix_confirmation_keys_intent_id", "confirmation_keys", ["intent_id"])
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("account", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(6), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_ledger_entries_direction"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_intent_id", "ledger_entries", ["intent_id"])
    op.execute(_FORBID_CHANGES)
    op.execute(_CHECK_BALANCE)
    for statement in _TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("ledger_entries")  # supprime aussi ses déclencheurs
    op.execute("DROP FUNCTION ledger_entries_check_balance()")
    op.execute("DROP FUNCTION ledger_entries_forbid_change()")
    op.drop_table("confirmation_keys")
