from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.intent.infrastructure.models.base import Base


class OutboxEventModel(Base):
    """Événements à livrer à la boutique (table `outbox`, migration 0006, ajout seul de schéma).

    `body` est le texte exact qui est signé puis envoyé à chaque tentative.
    """

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'dead', 'rejected_by_receiver')",
            name="ck_outbox_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts_positive"),
        Index("ix_outbox_status_next_attempt_at", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32))
    intent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("payment_intents.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
