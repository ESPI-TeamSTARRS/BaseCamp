from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.intent.infrastructure.models.base import Base


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    caller: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    intent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("payment_intents.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
