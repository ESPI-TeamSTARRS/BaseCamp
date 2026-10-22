from uuid import UUID

from app.catalog.application import admin_events
from app.catalog.application.invalid_product_error import InvalidProductError
from app.catalog.application.new_product import NewProduct
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_validator import ProductValidator
from app.catalog.domain.entities.product import Product
from app.catalog.domain.errors.duplicate_product_error import DuplicateProductError
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.catalog.domain.services.slugify import slugify
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer

_MAX_NAME = 200
_MAX_SHORT = 300
_MAX_DESCRIPTION = 5000


class CreateProductUseCase:
    """Crée un produit : l'identifiant est son slug (donné ou dérivé du nom), les notes partent de zéro."""

    def __init__(
        self,
        repository: AdminProductRepository,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._repository = repository
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, operator_id: UUID, command: NewProduct) -> Product:
        name = ProductValidator.text(command.name, "name_invalid", _MAX_NAME)
        slug = self._slug(command.slug, name)
        try:
            product = Product(
                id=slug,
                slug=slug,
                name=name,
                category=ProductValidator.category(command.category),
                price_cents=ProductValidator.price(command.price_cents),
                compare_at_price_cents=ProductValidator.optional_price(
                    command.compare_at_price_cents
                ),
                short_description=ProductValidator.text(
                    command.short_description, "short_description_invalid", _MAX_SHORT
                ),
                description=ProductValidator.text(
                    command.description, "description_invalid", _MAX_DESCRIPTION
                ),
                image_keys=(),
                specs=ProductValidator.specs(command.specs),
                stock=ProductValidator.stock(command.stock),
                rating_value=0.0,
                rating_count=0,
            )
        except ValueError:
            raise InvalidProductError("product_invalid") from None
        try:
            self._repository.add(product)
        except DuplicateProductError:
            raise ProductConflictError("duplicate_product") from None
        self._events.log(
            admin_events.change(
                admin_events.CREATE,
                self._pseudonymizer.pseudonymize(str(operator_id)),
                product,
                None,
            )
        )
        return product

    @staticmethod
    def _slug(requested: str | None, name: str) -> str:
        slug = requested if requested is not None else slugify(name)
        if not slug or slug != slugify(slug):
            raise InvalidProductError("slug_invalid")
        return slug
