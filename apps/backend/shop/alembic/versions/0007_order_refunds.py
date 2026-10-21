"""Remboursement d'une commande : statut « refunded » et cumul remboursé.

Elargit ck_orders_status (pending_payment, paid, expired, refunded) et ajoute la table
order_refunds (cumul remboursé par commande, absente tant que rien n'est remboursé). L'ancien code
n'écrit que les anciens statuts et ignore la table : il reste valide sur le schéma migré. Limite
assumée : il ne sait pas relire une commande « refunded » (il ne lit que pour rejouer une clé).

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status",
        "orders",
        "status IN ('pending_payment', 'paid', 'expired', 'refunded')",
    )
    op.create_table(
        "order_refunds",
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), primary_key=True),
        sa.Column("refunded_cents", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("refunded_cents > 0", name="ck_order_refunds_positive"),
    )


def downgrade() -> None:
    op.drop_table("order_refunds")
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_status", "orders", "status IN ('pending_payment', 'paid', 'expired')"
    )
