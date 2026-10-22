from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.backoffice.infrastructure.models.backoffice_base import BackofficeBase
from app.backoffice.infrastructure.models.utc_date_time import UtcDateTime


class BackofficeChallengeModel(BackofficeBase):
    """Defi a usage unique : seule l'empreinte de l'identifiant remis au client est stockee."""

    __tablename__ = "backoffice_challenges"
    __table_args__ = (Index("ix_backoffice_challenges_expires_at", "expires_at"),)

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    address_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    face_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
