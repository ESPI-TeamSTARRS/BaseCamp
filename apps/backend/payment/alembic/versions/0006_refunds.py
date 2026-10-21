"""Remboursements : table `refunds`, plafond au montant capturé garanti par la base.

Compatible avec la version précédente : nouvelle table seulement (aucune table existante
modifiée, aucune colonne ajoutée); la clé étrangère part de `refunds` vers `payment_intents`.
Le compte de grand livre `remboursements` n'exige aucun changement de schéma (`account` est un
texte libre, les déclencheurs de `ledger_entries` ne dépendent pas du nom du compte). L'ancienne
version ignore la table et continue de fonctionner.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Le cumul des remboursements d'une intention ne dépasse jamais son montant capturé, quel que soit
# le client SQL. La ligne de l'intention est verrouillée avant la somme : deux insertions
# concurrentes se suivent, la seconde voit la première validée.
_CHECK_CEILING = """
CREATE FUNCTION refunds_check_ceiling() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    captured bigint;
    total bigint;
BEGIN
    SELECT amount INTO captured FROM payment_intents WHERE id = NEW.intent_id FOR UPDATE;
    SELECT COALESCE(SUM(amount), 0) INTO total FROM refunds WHERE intent_id = NEW.intent_id;
    IF total > captured THEN
        RAISE EXCEPTION 'remboursements depassent le montant capture de l intention % : cumul % capture %',
            NEW.intent_id, total, captured;
    END IF;
    RETURN NULL;
END;
$$
"""

_FORBID_CHANGES = """
CREATE FUNCTION refunds_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'refunds est en ajout seul';
END;
$$
"""

_TRIGGERS = (
    """CREATE TRIGGER refunds_within_captured AFTER INSERT ON refunds
       FOR EACH ROW EXECUTE FUNCTION refunds_check_ceiling()""",
    """CREATE TRIGGER refunds_append_only BEFORE UPDATE OR DELETE ON refunds
       FOR EACH ROW EXECUTE FUNCTION refunds_forbid_change()""",
    """CREATE TRIGGER refunds_no_truncate BEFORE TRUNCATE ON refunds
       FOR EACH STATEMENT EXECUTE FUNCTION refunds_forbid_change()""",
)


def upgrade() -> None:
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("amount_refunded", sa.BigInteger(), nullable=False),
        sa.Column("caller", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("caller", "idempotency_key", name="uq_refunds_caller_key"),
        sa.CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
        sa.CheckConstraint("amount_refunded >= amount", name="ck_refunds_cumulated_covers_amount"),
    )
    op.create_index("ix_refunds_intent_id", "refunds", ["intent_id"])
    op.execute(_CHECK_CEILING)
    op.execute(_FORBID_CHANGES)
    for statement in _TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("refunds")  # supprime aussi ses déclencheurs
    op.execute("DROP FUNCTION refunds_check_ceiling()")
    op.execute("DROP FUNCTION refunds_forbid_change()")
