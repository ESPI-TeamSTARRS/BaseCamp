"""Connexion du back-office en trois temps : defis a usage unique et gabarits faciaux.

Expand/contract : deux tables nouvelles, rien n'est modifie ni supprime. L'ancienne version du service
les ignore et continue de fonctionner pendant le deploiement.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backoffice_challenges",
        sa.Column("digest", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("address_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("face_ok", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_backoffice_challenges_expires_at", "backoffice_challenges", ["expires_at"])
    op.create_table(
        "operator_face_templates",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("template", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("operator_face_templates")
    op.drop_index("ix_backoffice_challenges_expires_at", table_name="backoffice_challenges")
    op.drop_table("backoffice_challenges")
