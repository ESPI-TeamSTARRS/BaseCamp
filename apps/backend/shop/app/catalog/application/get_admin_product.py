from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository


class GetAdminProductUseCase:
    """Un produit par identifiant, archivé ou non."""

    def __init__(self, repository: AdminProductRepository) -> None:
        self._repository = repository

    def execute(self, product_id: str) -> Product:
        product = self._repository.get(product_id)
        if product is None:
            raise ProductNotFoundError
        return product
