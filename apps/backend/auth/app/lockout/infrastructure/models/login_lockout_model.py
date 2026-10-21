from datetime import datetime

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.lockout.infrastructure.models.lockout_base import LockoutBase
from app.lockout.infrastructure.models.utc_date_time import UtcDateTime


class LoginLockoutModel(LockoutBase):
    """Etat de verrouillage par etape et par sujet (empreinte opaque, jamais une adresse)."""

    __tablename__ = "login_lockouts"
    __table_args__ = (Index("ix_login_lockouts_updated_at", "updated_at"),)

    scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
