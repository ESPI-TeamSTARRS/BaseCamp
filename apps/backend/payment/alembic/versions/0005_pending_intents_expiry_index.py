"""Index partiel des intentions en attente, pour le traitement d'expiration.

Compatible avec la version précédente : un index est ajouté, aucune colonne, contrainte ni table
n'est modifiée ou supprimée. L'ancien code ignore l'index; seul le plan de requête change.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_payment_intents_pending_expiry"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "payment_intents",
        ["expires_at"],
        postgresql_where="status = 'requires_confirmation'",
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="payment_intents")
