"""Outbox : statut « rejected_by_receiver » (paiement refusé par la boutique, remboursé).

Elargit la colonne `status` (VARCHAR(16) vers VARCHAR(32), le nouveau statut en fait 20) et
ck_outbox_status (pending, delivered, dead, rejected_by_receiver). Aucune table ni colonne ajoutée :
l'ancien code n'écrit que les anciens statuts et ne relit que les événements `pending` (livraison)
et `dead` (relance), il reste valide sur le schéma migré.

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
    op.alter_column("outbox", "status", type_=sa.String(32), existing_type=sa.String(16))
    op.drop_constraint("ck_outbox_status", "outbox", type_="check")
    op.create_check_constraint(
        "ck_outbox_status",
        "outbox",
        "status IN ('pending', 'delivered', 'dead', 'rejected_by_receiver')",
    )


def downgrade() -> None:
    # Retour arrière : un événement refusé puis remboursé est terminé, l'ancien schéma le lit « delivered ».
    op.execute("UPDATE outbox SET status = 'delivered' WHERE status = 'rejected_by_receiver'")
    op.drop_constraint("ck_outbox_status", "outbox", type_="check")
    op.create_check_constraint(
        "ck_outbox_status", "outbox", "status IN ('pending', 'delivered', 'dead')"
    )
    op.alter_column("outbox", "status", type_=sa.String(16), existing_type=sa.String(32))
