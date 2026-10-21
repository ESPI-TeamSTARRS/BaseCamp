from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class PaymentWebhookEventModel(OrderBase):
    """Événement de `payment` déjà reçu : l'identifiant est la clé, donc un rejeu n'a aucun effet.

    `paid_order_id` est unique : une commande payée correspond à exactement un événement de paiement.
    """

    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('applied', 'ignored')", name="ck_payment_webhook_events_outcome"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("orders.id"), unique=True, nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
