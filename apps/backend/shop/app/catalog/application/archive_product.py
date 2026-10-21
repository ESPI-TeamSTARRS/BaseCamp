from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.catalog.application import admin_events
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ArchiveProductUseCase:
    """Archive un produit (soft delete) : il quitte le catalogue client, aucune ligne n'est effacée."""

    def __init__(
        self,
        repository: AdminProductRepository,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._events = events
        self._pseudonymizer = pseudonymizer
        self._clock = clock

    def execute(self, operator_id: UUID, product_id: str) -> Product:
        before = self._repository.get(product_id)
        if before is None:
            raise ProductNotFoundError
        product = self._repository.archive(product_id, self._clock())
        if product is None:
            raise ProductNotFoundError
        if before.archived_at is None:  # un second archivage ne change rien et ne se journalise pas
            self._events.log(
                admin_events.change(
                    admin_events.ARCHIVE,
                    self._pseudonymizer.pseudonymize(str(operator_id)),
                    product,
                    before.price_cents,
                )
            )
        return product
