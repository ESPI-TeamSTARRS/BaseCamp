from datetime import datetime

from pydantic import BaseModel


class AdminOrderLineResponse(BaseModel):
    name: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


class AdminShippingAddressResponse(BaseModel):
    full_name: str
    line1: str
    line2: str | None
    postal_code: str
    city: str
    country: str


class AdminOrderResponse(BaseModel):
    """Détail d'une commande pour l'opérateur : adresse de livraison comprise."""

    id: str
    number: str
    status: str
    email: str
    shipping_address: AdminShippingAddressResponse
    lines: list[AdminOrderLineResponse]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    created_at: datetime
