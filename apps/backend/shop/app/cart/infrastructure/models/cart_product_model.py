from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CartBase(DeclarativeBase):
    """Base declarative de la tranche cart (lecture seule de la table products)."""


class CartProductModel(CartBase):
    """Vue en lecture du catalogue : seules les colonnes utiles au devis sont mappees."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
