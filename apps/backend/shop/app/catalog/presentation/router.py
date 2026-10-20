from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.catalog.application.invalid_catalog_query_error import InvalidCatalogQueryError
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.presentation.dependencies import get_list_products_use_case
from app.catalog.presentation.schemas.product_list_response import ProductListResponse
from app.catalog.presentation.schemas.product_response import ProductResponse
from app.catalog.presentation.schemas.product_specs_response import ProductSpecsResponse
from app.core.config import Settings

router = APIRouter(tags=["catalog"])

DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 100


@router.get("/products", response_model=ProductListResponse)
def list_products(
    use_case: Annotated[ListProductsUseCase, Depends(get_list_products_use_case)],
    category: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> ProductListResponse:
    try:
        result = use_case.execute(category=category, page=page, page_size=page_size)
    except InvalidCatalogQueryError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.message) from None
    media_base_url = Settings().media_base_url.rstrip("/")
    items = [
        ProductResponse(
            id=product.id,
            slug=product.slug,
            name=product.name,
            category=product.category.value,
            price_cents=product.price_cents,
            compare_at_price_cents=product.compare_at_price_cents,
            short_description=product.short_description,
            description=product.description,
            thumbnail_url=_media_url(media_base_url, product.thumbnail_key),
            image_urls=[f"{media_base_url}/{key}" for key in product.image_keys],
            specs=ProductSpecsResponse(
                weight_grams=product.specs.weight_grams,
                waterproofing_mm=product.specs.waterproofing_mm,
                comfort_temp_c=product.specs.comfort_temp_c,
                seasons=product.specs.seasons,
                capacity_liters=product.specs.capacity_liters,
                material=product.specs.material,
            ),
            rating_value=product.rating_value,
            rating_count=product.rating_count,
            availability=product.availability.value,
        )
        for product in result.items
    ]
    return ProductListResponse(
        items=items, page=result.page, page_size=result.page_size, total=result.total
    )


def _media_url(media_base_url: str, key: str | None) -> str | None:
    return f"{media_base_url}/{key}" if key else None
