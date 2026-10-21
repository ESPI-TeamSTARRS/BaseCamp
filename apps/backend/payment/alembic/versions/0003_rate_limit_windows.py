"""Compteurs de limitation de débit par appelant, route et fenêtre (partagés entre instances).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_windows",
        sa.Column("caller", sa.String(64), nullable=False),
        sa.Column("route", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("caller", "route", "window_start"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_windows")
