"""Administration du catalogue : archivage (soft delete), version optimiste, prix à zéro permis.

Ajoute `products.archived_at` (nullable : null = produit visible) et `products.version` (entier avec
défaut serveur 1, incrémenté à chaque modification : concurrence optimiste de l'API d'administration
et des variations de stock). Élargit `ck_products_price_positive` à `price_cents >= 0`. L'ancien code
n'écrit ni `archived_at` ni `version` : les défauts s'appliquent, il reste valide sur le schéma migré.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "products", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.drop_constraint("ck_products_price_positive", "products", type_="check")
    op.create_check_constraint("ck_products_price_positive", "products", "price_cents >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_products_price_positive", "products", type_="check")
    op.create_check_constraint("ck_products_price_positive", "products", "price_cents > 0")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("version")
        batch.drop_column("archived_at")
