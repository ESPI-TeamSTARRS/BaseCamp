from sqlalchemy.orm import DeclarativeBase


class OrderBase(DeclarativeBase):
    """Base declarative de la tranche order (orders, order_lines, stock_reservations)."""
