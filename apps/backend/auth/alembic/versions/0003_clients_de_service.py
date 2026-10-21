"""Clients de service (jetons entre services) et compteurs de limitation de debit par client.

Autonome : ne depend que de 0001 pour l'instant. Si une autre migration s'insere avant elle,
renumeroter ce fichier et son `down_revision` (aucune autre migration ne la reference).
Aucun secret ici : les clients sont amorces par `python -m app.service_token.bootstrap`.

Revision ID: 0003
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("scopes", sa.String(255), nullable=False),
        sa.Column("current_secret_hash", sa.String(255), nullable=False),
        sa.Column("previous_secret_hash", sa.String(255), nullable=True),
    )
    op.create_table(
        "service_token_rate_limits",
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("client_id", "window_start"),
    )
    op.create_index(
        "ix_service_token_rate_limits_window_start", "service_token_rate_limits", ["window_start"]
    )


def downgrade() -> None:
    op.drop_index("ix_service_token_rate_limits_window_start", "service_token_rate_limits")
    op.drop_table("service_token_rate_limits")
    op.drop_table("service_clients")
