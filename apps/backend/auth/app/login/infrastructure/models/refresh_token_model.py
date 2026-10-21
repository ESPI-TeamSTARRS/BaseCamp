from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.login.infrastructure.models.login_base import LoginBase
from app.login.infrastructure.models.utc_date_time import UtcDateTime


class RefreshTokenModel(LoginBase):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    family_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
