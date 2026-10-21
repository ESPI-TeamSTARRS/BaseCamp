"""Outbox : statut « rejected_by_receiver » (paiement refusé par la boutique, remboursé).

Elargit ck_outbox_status (pending, delivered, dead, rejected_by_receiver). Aucune table ni colonne
ajoutée : l'ancien code n'écrit que les anciens statuts et ne relit que les événements `pending`
(livraison) et `dead` (relance), il reste valide sur le schéma migré.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_outbox_status", "outbox", type_="check")
    op.create_check_constraint(
        "ck_outbox_status",
        "outbox",
        "status IN ('pending', 'delivered', 'dead', 'rejected_by_receiver')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_outbox_status", "outbox", type_="check")
    op.create_check_constraint(
        "ck_outbox_status", "outbox", "status IN ('pending', 'delivered', 'dead')"
    )
