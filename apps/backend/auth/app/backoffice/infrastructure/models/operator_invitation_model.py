from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.backoffice.infrastructure.models.backoffice_base import BackofficeBase
from app.backoffice.infrastructure.models.utc_date_time import UtcDateTime


class OperatorInvitationModel(BackofficeBase):
    """Invitation d'operateur : seule l'empreinte du jeton est stockee."""

    __tablename__ = "operator_invitations"
    __table_args__ = (
        Index("ix_operator_invitations_email", "email"),
        Index("ix_operator_invitations_expires_at", "expires_at"),
    )

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
