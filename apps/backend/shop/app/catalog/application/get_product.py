from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.product_lookup import ProductLookup


class GetProductUseCase:
    """Fiche detaillee d'un produit a partir de son slug."""

    def __init__(self, lookup: ProductLookup) -> None:
        self._lookup = lookup

    def execute(self, slug: str) -> Product:
        product = self._lookup.get_by_slug(slug)
        if product is None:
            raise ProductNotFoundError
        return product
