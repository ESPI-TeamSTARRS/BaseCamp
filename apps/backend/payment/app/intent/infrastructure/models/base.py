from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base déclarative des modèles de payment (métadonnées lues par Alembic)."""
