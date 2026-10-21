"""Rafraichissement : famille et usage des jetons (detection de reutilisation).

Expand/contract : deux colonnes nullables et un index, rien n'est supprime ni renomme. Les lignes
existantes (famille et usage nuls) restent valides : un jeton sans famille forme sa propre famille.
L'ancienne version du service, qui ignore ces colonnes, continue de fonctionner.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_column("used_at")
        batch.drop_column("family_id")
