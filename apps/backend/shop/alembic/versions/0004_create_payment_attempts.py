"""Paiement d'une commande : tentatives, fournisseur simulé et statuts payée / expirée.

Ajoute les tables payment_attempts et simulated_payment_intents. Elargit aussi la contrainte
ck_orders_status (pending_payment, paid, expired) : l'ancien code n'ecrit que pending_payment et
reste valide sur le schema migre. Limite assumee : l'ancien code ne sait pas relire une commande
deja payee ou expiree (il ne la lit que pour rejouer une cle d'idempotence).

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


def upgrade() -> None:
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, unique=True),
        sa.Column("intent_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "number", name="uq_payment_attempts_order_number"),
        sa.CheckConstraint("number > 0", name="ck_payment_attempts_number_positive"),
        sa.CheckConstraint(
            "status IN ('requires_confirmation', 'succeeded', 'failed')",
            name="ck_payment_attempts_status",
        ),
    )
    op.create_index("ix_payment_attempts_order_id", "payment_attempts", ["order_id"])
    op.create_table(
        "simulated_payment_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_reference", sa.String(64), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_simulated_intents_amount_positive"),
    )
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status", "orders", "status IN ('pending_payment', 'paid', 'expired')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint("ck_orders_status", "orders", "status IN ('pending_payment')")
    op.drop_table("simulated_payment_intents")
    op.drop_index("ix_payment_attempts_order_id", table_name="payment_attempts")
    op.drop_table("payment_attempts")
