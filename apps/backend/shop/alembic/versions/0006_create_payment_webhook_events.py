"""Confirmation de paiement par webhook : mémoire des événements et réservations « committed ».

Ajoute la table payment_webhook_events (identifiant d'événement en clé primaire : un rejeu n'a aucun
effet; paid_order_id unique : une commande payée correspond à exactement un événement de paiement)
et élargit la contrainte ck_stock_reservations_status à « committed » (stock rendu définitif).
L'ancien code n'écrit que « reserved » (et « released ») et reste valide sur le schéma migré.

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
        "payment_webhook_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("paid_order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("paid_order_id", name="uq_payment_webhook_events_paid_order_id"),
        sa.CheckConstraint(
            "outcome IN ('applied', 'ignored')", name="ck_payment_webhook_events_outcome"
        ),
    )
    op.drop_constraint("ck_stock_reservations_status", "stock_reservations", type_="check")
    op.create_check_constraint(
        "ck_stock_reservations_status",
        "stock_reservations",
        "status IN ('reserved', 'released', 'committed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stock_reservations_status", "stock_reservations", type_="check")
    op.create_check_constraint(
        "ck_stock_reservations_status",
        "stock_reservations",
        "status IN ('reserved', 'released')",
    )
    op.drop_table("payment_webhook_events")
