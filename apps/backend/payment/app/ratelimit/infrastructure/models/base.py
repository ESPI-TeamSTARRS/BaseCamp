from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base déclarative de la tranche ratelimit (métadonnées lues par Alembic)."""
