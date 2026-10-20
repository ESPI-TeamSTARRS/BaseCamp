"""Tables des intentions de paiement et des clés d'idempotence (montants en centimes entiers).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_reference", sa.String(64), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("refunded_amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_reference", name="uq_payment_intents_order_reference"),
        sa.CheckConstraint("amount > 0", name="ck_payment_intents_amount_positive"),
        sa.CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="ck_payment_intents_refunded_within_amount",
        ),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("caller", sa.String(64), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("caller", "key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("payment_intents")
