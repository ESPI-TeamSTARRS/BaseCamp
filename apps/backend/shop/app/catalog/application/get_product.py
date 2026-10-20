from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.product_lookup import ProductLookup
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger

PRODUCT_RESOURCE = "product"


class GetProductUseCase:
    """Fiche detaillee d'un produit a partir de son slug."""

    def __init__(self, lookup: ProductLookup, events: BusinessEventLogger) -> None:
        self._lookup = lookup
        self._events = events

    def execute(self, slug: str) -> Product:
        product = self._lookup.get_by_slug(slug)
        if product is None:
            self._events.log(
                BusinessEvent.denied(
                    "catalog.product_not_found", "product_not_found", resource_type=PRODUCT_RESOURCE
                )
            )
            raise ProductNotFoundError
        self._events.log(
            BusinessEvent.success(
                "catalog.product_viewed", resource_type=PRODUCT_RESOURCE, resource_id=product.id
            )
        )
        return product
