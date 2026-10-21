from pydantic import BaseModel

from app.catalog.presentation.schemas.admin_product_response import AdminProductResponse


class AdminProductListResponse(BaseModel):
    items: list[AdminProductResponse]
    total: int
    limit: int
    offset: int
