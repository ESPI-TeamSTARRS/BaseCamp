from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class OrderRefundModel(OrderBase):
    """Cumul remboursé d'une commande (une ligne dès le premier remboursement)."""

    __tablename__ = "order_refunds"

    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), primary_key=True)
    refunded_cents: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
