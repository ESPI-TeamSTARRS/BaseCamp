from dataclasses import dataclass

from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository


@dataclass(frozen=True)
class AdminProductPage:
    items: list[Product]
    total: int
    limit: int
    offset: int


class ListAdminProductsUseCase:
    """Liste paginée du catalogue complet, produits archivés optionnels."""

    def __init__(self, repository: AdminProductRepository) -> None:
        self._repository = repository

    def execute(self, include_archived: bool, limit: int, offset: int) -> AdminProductPage:
        return AdminProductPage(
            items=self._repository.list_products(include_archived, limit, offset),
            total=self._repository.count(include_archived),
            limit=limit,
            offset=offset,
        )
