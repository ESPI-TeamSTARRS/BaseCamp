from typing import cast

from fastapi import Request

from app.catalog.application.archive_product import ArchiveProductUseCase
from app.catalog.application.create_product import CreateProductUseCase
from app.catalog.application.get_admin_product import GetAdminProductUseCase
from app.catalog.application.list_admin_products import ListAdminProductsUseCase
from app.catalog.application.update_product import UpdateProductUseCase
from app.catalog.application.upload_product_image import UploadProductImageUseCase


def list_admin_products_use_case(request: Request) -> ListAdminProductsUseCase:
    """Les cas d'usage sont câblés dans main.py (la présentation n'importe pas l'infrastructure)."""
    return cast(ListAdminProductsUseCase, request.app.state.list_admin_products_use_case)


def get_admin_product_use_case(request: Request) -> GetAdminProductUseCase:
    return cast(GetAdminProductUseCase, request.app.state.get_admin_product_use_case)


def create_product_use_case(request: Request) -> CreateProductUseCase:
    return cast(CreateProductUseCase, request.app.state.create_product_use_case)


def update_product_use_case(request: Request) -> UpdateProductUseCase:
    return cast(UpdateProductUseCase, request.app.state.update_product_use_case)


def archive_product_use_case(request: Request) -> ArchiveProductUseCase:
    return cast(ArchiveProductUseCase, request.app.state.archive_product_use_case)


def upload_product_image_use_case(request: Request) -> UploadProductImageUseCase:
    return cast(UploadProductImageUseCase, request.app.state.upload_product_image_use_case)
