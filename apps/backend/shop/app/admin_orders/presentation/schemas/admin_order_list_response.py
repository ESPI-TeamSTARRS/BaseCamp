from datetime import datetime

from pydantic import BaseModel


class AdminOrderSummaryResponse(BaseModel):
    """Ligne de la liste : jamais l'adresse de livraison."""

    id: str
    number: str
    status: str
    email: str
    total_cents: int
    item_count: int
    created_at: datetime


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderSummaryResponse]
    total: int
    limit: int
    offset: int
