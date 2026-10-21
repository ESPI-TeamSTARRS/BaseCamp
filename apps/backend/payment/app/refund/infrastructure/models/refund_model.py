from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.intent.infrastructure.models.base import Base


class RefundModel(Base):
    """Remboursements émis (table `refunds`, migration 0006, ajout seul de schéma).

    Sur Postgres, des déclencheurs posés par la migration refusent tout cumul supérieur au montant
    capturé de l'intention (le verrou de ligne de l'application n'est qu'une première barrière) et
    toute modification ou suppression d'une ligne. Les tests SQLite ne reproduisent pas ces
    déclencheurs : le plafond y est tenu par le cas d'usage et par la contrainte de l'intention.
    """

    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("caller", "idempotency_key", name="uq_refunds_caller_key"),
        CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
        CheckConstraint("amount_refunded >= amount", name="ck_refunds_cumulated_covers_amount"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    intent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("payment_intents.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    amount_refunded: Mapped[int] = mapped_column(BigInteger)
    caller: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
