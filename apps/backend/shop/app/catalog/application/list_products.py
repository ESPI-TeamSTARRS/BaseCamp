from app.catalog.application.invalid_catalog_query_error import InvalidCatalogQueryError
from app.catalog.domain.entities.product import (
    Product as Product,  # re-export: la presentation ne voit que l application
)
from app.catalog.domain.entities.product_page import ProductPage
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.interfaces.product_repository import ProductRepository
from app.core.events.business_event import BusinessEvent, Scalar
from app.core.events.business_event_logger import BusinessEventLogger

MAX_PAGE_SIZE = 100


class ListProductsUseCase:
    """Liste paginee des produits, filtrable par categorie."""

    def __init__(self, repository: ProductRepository, events: BusinessEventLogger) -> None:
        self._repository = repository
        self._events = events

    def execute(self, category: str | None, page: int, page_size: int) -> ProductPage:
        try:
            result = self._list(category, page, page_size)
        except InvalidCatalogQueryError:
            self._events.log(BusinessEvent.denied("catalog.query_rejected", "invalid_query"))
            raise
        attributes: dict[str, Scalar] = {
            "page": page,
            "page_size": page_size,
            "total": result.total,
        }
        if category is not None:
            attributes["category"] = category
        self._events.log(BusinessEvent.success("catalog.products_listed", attributes=attributes))
        return result

    def _list(self, category: str | None, page: int, page_size: int) -> ProductPage:
        parsed_category = self._parse_category(category)
        if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise InvalidCatalogQueryError("Pagination invalide.")
        products = self._repository.list_products(
            parsed_category, limit=page_size, offset=(page - 1) * page_size
        )
        return ProductPage(
            items=tuple(products),
            page=page,
            page_size=page_size,
            total=self._repository.count(parsed_category),
        )

    @staticmethod
    def _parse_category(category: str | None) -> ProductCategory | None:
        if category is None:
            return None
        try:
            return ProductCategory(category)
        except ValueError:
            raise InvalidCatalogQueryError("Categorie inconnue.") from None
