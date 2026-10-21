from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class OrderLineModel(OrderBase):
    """Ligne de commande : nom et prix unitaire figes au moment de la commande."""

    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
