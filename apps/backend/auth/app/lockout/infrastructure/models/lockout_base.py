from sqlalchemy.orm import DeclarativeBase


class LockoutBase(DeclarativeBase):
    """Base declarative de la tranche lockout : elle ne declare que sa propre table."""
