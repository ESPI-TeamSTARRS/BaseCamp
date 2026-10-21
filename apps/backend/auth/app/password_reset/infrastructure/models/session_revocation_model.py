from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.models.utc_date_time import UtcDateTime


class SessionRevocationModel(AuthBase):
    """Seuil de revocation par compte : toute session emise avant `revoked_at` est invalide."""

    __tablename__ = "session_revocations"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    revoked_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
