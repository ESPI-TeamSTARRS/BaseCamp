from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class PaymentAttemptModel(OrderBase):
    """Une tentative de paiement d'une commande (une intention chez le fournisseur)."""

    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("order_id", "number", name="uq_payment_attempts_order_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    intent_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
