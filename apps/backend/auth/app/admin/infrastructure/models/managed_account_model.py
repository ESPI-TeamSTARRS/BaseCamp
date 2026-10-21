from datetime import datetime
from uuid import UUID

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.admin.infrastructure.models.admin_base import AdminBase
from app.admin.infrastructure.models.utc_date_time import UtcDateTime


class ManagedAccountModel(AdminBase):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
