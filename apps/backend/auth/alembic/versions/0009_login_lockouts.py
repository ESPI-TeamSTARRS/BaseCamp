"""Verrouillage progressif : etat par etape et par sujet.

Expand/contract : une table nouvelle, rien n'est modifie ni supprime. L'ancienne version du service
ignore la table et continue de fonctionner pendant le deploiement.

Revision ID: 0009
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_lockouts",
        sa.Column("scope", sa.String(32), primary_key=True),
        sa.Column("subject", sa.String(64), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_lockouts_updated_at", "login_lockouts", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_login_lockouts_updated_at", table_name="login_lockouts")
    op.drop_table("login_lockouts")
