from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.models.utc_date_time import UtcDateTime


class PasswordResetAttemptModel(AuthBase):
    """Une demande de lien, par empreinte d'adresse (jamais l'adresse) : base de la limite par email."""

    __tablename__ = "password_reset_attempts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, index=True)
