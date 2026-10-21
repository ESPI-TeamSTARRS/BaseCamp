from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class OrderModel(OrderBase):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    number: Mapped[str] = mapped_column(String(16), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(254))
    ship_full_name: Mapped[str] = mapped_column(String(120))
    ship_line1: Mapped[str] = mapped_column(String(200))
    ship_line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ship_postal_code: Mapped[str] = mapped_column(String(20))
    ship_city: Mapped[str] = mapped_column(String(120))
    ship_country: Mapped[str] = mapped_column(String(2))
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    shipping_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
