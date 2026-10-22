"""Invitations d'operateur a usage unique, generees en CLI par un administrateur IT.

Expand/contract : une table nouvelle, rien n'est modifie ni supprime. L'ancienne version du service
l'ignore et continue de fonctionner pendant le deploiement. Seule l'empreinte du jeton est stockee.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operator_invitations",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_operator_invitations_email", "operator_invitations", ["email"])
    op.create_index("ix_operator_invitations_expires_at", "operator_invitations", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_operator_invitations_expires_at", table_name="operator_invitations")
    op.drop_index("ix_operator_invitations_email", table_name="operator_invitations")
    op.drop_table("operator_invitations")
