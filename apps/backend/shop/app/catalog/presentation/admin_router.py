from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from app.catalog.application.archive_product import ArchiveProductUseCase
from app.catalog.application.create_product import CreateProductUseCase
from app.catalog.application.get_admin_product import GetAdminProductUseCase
from app.catalog.application.image_storage_unavailable_error import ImageStorageUnavailableError
from app.catalog.application.invalid_image_upload_error import InvalidImageUploadError
from app.catalog.application.invalid_product_error import InvalidProductError
from app.catalog.application.list_admin_products import ListAdminProductsUseCase
from app.catalog.application.list_products import Product
from app.catalog.application.new_product import NewProduct
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.application.update_product import UpdateProductUseCase
from app.catalog.application.update_product_command import UpdateProductCommand
from app.catalog.application.upload_product_image import MAX_IMAGE_BYTES, UploadProductImageUseCase
from app.catalog.presentation.admin_dependencies import (
    archive_product_use_case,
    create_product_use_case,
    get_admin_product_use_case,
    list_admin_products_use_case,
    update_product_use_case,
    upload_product_image_use_case,
)
from app.catalog.presentation.admin_product_response_mapper import AdminProductResponseMapper
from app.catalog.presentation.schemas.admin_product_create_request import (
    AdminProductCreateRequest,
)
from app.catalog.presentation.schemas.admin_product_list_response import AdminProductListResponse
from app.catalog.presentation.schemas.admin_product_response import AdminProductResponse
from app.catalog.presentation.schemas.admin_product_update_request import (
    AdminProductUpdateRequest,
)
from app.core.config import Settings
from app.customer_identity.application.operator_view import Operator
from app.customer_identity.presentation.dependencies import current_operator

router = APIRouter(prefix="/admin/products", tags=["catalog-admin"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_SEARCH_LENGTH = 100
NO_STORE = {"Cache-Control": "no-store"}
CurrentOperator = Annotated[Operator, Depends(current_operator)]


def _respond(product: Product) -> AdminProductResponse:
    return AdminProductResponseMapper(Settings().media_base_url).to_response(product)


def _failure(error: Exception) -> HTTPException:
    """Réponses fixes : jamais la valeur reçue, jamais le motif interne d'un refus de forme."""
    if isinstance(error, ProductNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=error.message, headers=NO_STORE)
    if isinstance(error, ProductConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=error.message, headers=NO_STORE)
    if isinstance(error, InvalidProductError | InvalidImageUploadError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message, headers=NO_STORE
        )
    if isinstance(error, ImageStorageUnavailableError):
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error.message,
            headers={**NO_STORE, "Retry-After": "5"},
        )
    raise error


@router.get("", response_model=AdminProductListResponse)
def list_products(
    operator: CurrentOperator,
    use_case: Annotated[ListAdminProductsUseCase, Depends(list_admin_products_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    include_archived: bool = False,
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
) -> AdminProductListResponse:
    page = use_case.execute(include_archived, limit, offset, q.strip() if q else None)
    return AdminProductListResponse(
        items=[_respond(p) for p in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", response_model=AdminProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    operator: CurrentOperator,
    body: AdminProductCreateRequest,
    use_case: Annotated[CreateProductUseCase, Depends(create_product_use_case)],
) -> AdminProductResponse:
    command = NewProduct(
        name=body.name,
        slug=body.slug,
        category=body.category,
        price_cents=body.price_cents,
        compare_at_price_cents=body.compare_at_price_cents,
        short_description=body.short_description,
        description=body.description,
        specs=body.specs.model_dump(exclude_none=True),
        stock=body.stock,
    )
    try:
        return _respond(use_case.execute(operator.id, command))
    except (InvalidProductError, ProductConflictError) as error:
        raise _failure(error) from None


@router.get("/{product_id}", response_model=AdminProductResponse)
def get_product(
    product_id: str,
    operator: CurrentOperator,
    use_case: Annotated[GetAdminProductUseCase, Depends(get_admin_product_use_case)],
) -> AdminProductResponse:
    try:
        return _respond(use_case.execute(product_id))
    except ProductNotFoundError as error:
        raise _failure(error) from None


@router.patch("/{product_id}", response_model=AdminProductResponse)
def update_product(
    product_id: str,
    operator: CurrentOperator,
    body: AdminProductUpdateRequest,
    use_case: Annotated[UpdateProductUseCase, Depends(update_product_use_case)],
) -> AdminProductResponse:
    changes: dict[str, Any] = body.model_dump(exclude_unset=True, exclude={"version"})
    command = UpdateProductCommand(product_id, body.version, changes)
    try:
        return _respond(use_case.execute(operator.id, command))
    except (InvalidProductError, ProductNotFoundError, ProductConflictError) as error:
        raise _failure(error) from None


@router.post("/{product_id}/archive", response_model=AdminProductResponse)
def archive_product(
    product_id: str,
    operator: CurrentOperator,
    use_case: Annotated[ArchiveProductUseCase, Depends(archive_product_use_case)],
) -> AdminProductResponse:
    try:
        return _respond(use_case.execute(operator.id, product_id))
    except ProductNotFoundError as error:
        raise _failure(error) from None


@router.post("/{product_id}/image", response_model=AdminProductResponse)
async def upload_image(
    product_id: str,
    request: Request,
    operator: CurrentOperator,
    use_case: Annotated[UploadProductImageUseCase, Depends(upload_product_image_use_case)],
) -> AdminProductResponse:
    """Corps = les octets de l'image (JPEG, PNG ou WebP, 2 Mo au plus); le type est lu dans le contenu."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
        raise _failure(InvalidImageUploadError("too_large"))
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_IMAGE_BYTES:  # on ne lit jamais plus que la limite
            raise _failure(InvalidImageUploadError("too_large"))
    try:
        product = await run_in_threadpool(use_case.execute, operator.id, product_id, bytes(content))
    except (
        InvalidImageUploadError,
        ProductNotFoundError,
        ProductConflictError,
        ImageStorageUnavailableError,
    ) as error:
        raise _failure(error) from None
    return _respond(product)
