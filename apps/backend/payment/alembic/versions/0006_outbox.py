"""Outbox des webhooks sortants : événements à livrer à la boutique, écrits avec l'état du paiement.

Compatible avec la version précédente : nouvelle table seulement (aucune table existante
modifiée, aucune colonne ajoutée); la clé étrangère part de `outbox` vers `payment_intents`.
L'ancienne version ignore la table et continue de fonctionner.

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


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'dead')", name="ck_outbox_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_positive"),
    )
    op.create_index("ix_outbox_intent_id", "outbox", ["intent_id"])
    op.create_index("ix_outbox_status_next_attempt_at", "outbox", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("outbox")
