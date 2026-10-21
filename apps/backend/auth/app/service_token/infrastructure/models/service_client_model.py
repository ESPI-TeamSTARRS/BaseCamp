from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.service_token.infrastructure.models.base import Base


class ServiceClientModel(Base):
    __tablename__ = "service_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scopes: Mapped[str] = mapped_column(String(255))
    current_secret_hash: Mapped[str] = mapped_column(String(255))
    previous_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
