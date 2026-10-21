from datetime import datetime

from pydantic import BaseModel


class AccountOrderLineResponse(BaseModel):
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


class AccountOrderResponse(BaseModel):
    """Commande d'un compte : jamais l'email ni l'adresse de livraison."""

    id: str
    number: str
    status: str
    lines: list[AccountOrderLineResponse]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime


class AccountOrderPageResponse(BaseModel):
    items: list[AccountOrderResponse]
    total: int
    limit: int
    offset: int
