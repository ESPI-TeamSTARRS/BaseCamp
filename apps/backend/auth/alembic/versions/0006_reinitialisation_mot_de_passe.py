"""Reinitialisation du mot de passe : jetons, demandes (limite par adresse) et revocation de sessions.

Expand/contract : uniquement des ajouts (trois tables), aucune colonne supprimee ni renommee.

Revision ID: 0006
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_table(
        "password_reset_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email_fingerprint", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_password_reset_attempts_email_fingerprint",
        "password_reset_attempts",
        ["email_fingerprint"],
    )
    op.create_index(
        "ix_password_reset_attempts_requested_at", "password_reset_attempts", ["requested_at"]
    )
    op.create_table(
        "session_revocations",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("session_revocations")
    op.drop_index("ix_password_reset_attempts_requested_at", table_name="password_reset_attempts")
    op.drop_index(
        "ix_password_reset_attempts_email_fingerprint", table_name="password_reset_attempts"
    )
    op.drop_table("password_reset_attempts")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
