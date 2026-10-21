from datetime import datetime

from pydantic import BaseModel

from app.order_tracking.presentation.schemas.tracked_line_response import TrackedLineResponse


class TrackedOrderResponse(BaseModel):
    """Statut, lignes et total : ni email ni adresse ne sont renvoyés."""

    number: str
    status: str
    lines: list[TrackedLineResponse]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
