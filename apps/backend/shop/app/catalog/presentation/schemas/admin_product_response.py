from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminProductResponse(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    price_cents: int
    compare_at_price_cents: int | None
    short_description: str
    description: str
    specs: dict[str, Any]
    stock: int
    availability: str
    image_keys: list[str]
    image_urls: list[str]
    version: int
    archived_at: datetime | None
