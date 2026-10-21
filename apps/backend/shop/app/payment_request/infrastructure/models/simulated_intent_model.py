from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class SimulatedIntentModel(OrderBase):
    """État du fournisseur simulé : en base, jamais en mémoire (plusieurs instances possibles)."""

    __tablename__ = "simulated_payment_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_reference: Mapped[str] = mapped_column(String(64), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
