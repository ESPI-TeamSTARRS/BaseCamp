from pydantic import BaseModel

from app.catalog.presentation.schemas.product_specs_response import ProductSpecsResponse


class ProductResponse(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    price_cents: int
    compare_at_price_cents: int | None
    short_description: str
    description: str
    thumbnail_url: str | None
    image_urls: list[str]
    specs: ProductSpecsResponse
    rating_value: float
    rating_count: int
    availability: str
