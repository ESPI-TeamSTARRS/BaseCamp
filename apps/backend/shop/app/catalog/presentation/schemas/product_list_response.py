from pydantic import BaseModel

from app.catalog.presentation.schemas.product_response import ProductResponse


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    page: int
    page_size: int
    total: int
