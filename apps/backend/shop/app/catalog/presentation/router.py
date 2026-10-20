from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.catalog.application.get_product import GetProductUseCase
from app.catalog.application.invalid_catalog_query_error import InvalidCatalogQueryError
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.presentation.dependencies import (
    get_get_product_use_case,
    get_list_products_use_case,
)
from app.catalog.presentation.product_response_mapper import ProductResponseMapper
from app.catalog.presentation.schemas.product_list_response import ProductListResponse
from app.catalog.presentation.schemas.product_response import ProductResponse
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
    mapper = ProductResponseMapper(Settings().media_base_url)
    return ProductListResponse(
        items=[mapper.to_response(product) for product in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/products/{slug}", response_model=ProductResponse)
def get_product(
    slug: str,
    use_case: Annotated[GetProductUseCase, Depends(get_get_product_use_case)],
) -> ProductResponse:
    try:
        product = use_case.execute(slug)
    except ProductNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message) from None
    return ProductResponseMapper(Settings().media_base_url).to_response(product)
