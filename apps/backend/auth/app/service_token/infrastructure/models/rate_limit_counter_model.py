from sqlalchemy import BigInteger, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.service_token.infrastructure.models.base import Base


class RateLimitCounterModel(Base):
    __tablename__ = "service_token_rate_limits"
    __table_args__ = (Index("ix_service_token_rate_limits_window_start", "window_start"),)

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hits: Mapped[int] = mapped_column(Integer)
