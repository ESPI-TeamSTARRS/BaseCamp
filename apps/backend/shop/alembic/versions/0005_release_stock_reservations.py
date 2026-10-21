"""Libération du stock des commandes expirées : statut « released » des réservations.

Elargit la contrainte ck_stock_reservations_status (reserved, released). L'ancien code n'écrit
que « reserved » et reste valide sur le schéma migré; aucune table ni colonne n'est ajoutée.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_stock_reservations_status", "stock_reservations", type_="check")
    op.create_check_constraint(
        "ck_stock_reservations_status",
        "stock_reservations",
        "status IN ('reserved', 'released')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stock_reservations_status", "stock_reservations", type_="check")
    op.create_check_constraint(
        "ck_stock_reservations_status", "stock_reservations", "status IN ('reserved')"
    )
