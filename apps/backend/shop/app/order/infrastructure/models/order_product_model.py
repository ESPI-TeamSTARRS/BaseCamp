from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.order.infrastructure.models.order_base import OrderBase


class OrderProductModel(OrderBase):
    """Colonnes de la table products utiles a la commande (le stock y est decremente)."""

    __tablename__ = "products"
    __table_args__ = (CheckConstraint("stock >= 0", name="ck_products_stock_non_negative"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
