from dataclasses import replace
from typing import Any
from uuid import UUID

from app.catalog.application import admin_events
from app.catalog.application.invalid_product_error import InvalidProductError
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.application.product_validator import ProductValidator
from app.catalog.application.update_product_command import UpdateProductCommand
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer

EDITABLE_FIELDS = frozenset(
    {
        "name",
        "category",
        "price_cents",
        "compare_at_price_cents",
        "short_description",
        "description",
        "specs",
        "stock",
    }
)


class UpdateProductUseCase:
    """Modification partielle sous concurrence optimiste : une version périmée est refusée (409)."""

    def __init__(
        self,
        repository: AdminProductRepository,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._repository = repository
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, operator_id: UUID, command: UpdateProductCommand) -> Product:
        if not command.changes or not set(command.changes) <= EDITABLE_FIELDS:
            raise InvalidProductError("changes_invalid")
        current = self._repository.get(command.product_id)
        if current is None:
            raise ProductNotFoundError
        if current.archived_at is not None:
            raise ProductConflictError("product_archived")
        try:
            candidate = replace(current, **self._values(command.changes))
        except ValueError:
            raise InvalidProductError("product_invalid") from None
        saved = self._repository.update(candidate, command.expected_version)
        if saved is None:
            raise ProductConflictError("stale_version")
        self._events.log(
            admin_events.change(
                admin_events.UPDATE,
                self._pseudonymizer.pseudonymize(str(operator_id)),
                saved,
                current.price_cents,
            )
        )
        return saved

    @staticmethod
    def _values(changes: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field, value in changes.items():
            if field == "name":
                values[field] = ProductValidator.text(value, "name_invalid", 200)
            elif field == "category":
                values[field] = ProductValidator.category(value)
            elif field == "price_cents":
                values[field] = ProductValidator.price(value)
            elif field == "compare_at_price_cents":
                values[field] = ProductValidator.optional_price(value)
            elif field == "short_description":
                values[field] = ProductValidator.text(value, "short_description_invalid", 300)
            elif field == "description":
                values[field] = ProductValidator.text(value, "description_invalid", 5000)
            elif field == "specs":
                values[field] = ProductValidator.specs(value)
            else:
                values["stock"] = ProductValidator.stock(value)
        return values
