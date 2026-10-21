"""Commandes rattachees a un compte : `orders.user_id` (identifiant du compte d'`auth`).

Expand/contract : une colonne nullable et un index, rien n'est supprime ni renomme. Les commandes
existantes (invitees) gardent `user_id` nul; l'ancienne version du service, qui ignore la colonne,
continue de fonctionner sur le schema migre. Aucune cle etrangere : le compte vit dans `auth`
(autre base), seul son identifiant est conserve, sans copie d'autre donnee du compte.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("user_id", sa.String(36), nullable=True))
    op.create_index("ix_orders_user_id", "orders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_user_id", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("user_id")
