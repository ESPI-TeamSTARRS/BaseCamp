from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.intent.infrastructure.models.base import Base


class PaymentIntentModel(Base):
    __tablename__ = "payment_intents"
    __table_args__ = (
        UniqueConstraint("order_reference", name="uq_payment_intents_order_reference"),
        CheckConstraint("amount > 0", name="ck_payment_intents_amount_positive"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="ck_payment_intents_refunded_within_amount",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    order_reference: Mapped[str] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32))
    refunded_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
