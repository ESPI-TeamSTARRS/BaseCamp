import secrets
from collections.abc import Callable
from uuid import UUID

from app.catalog.application import admin_events
from app.catalog.application.image_storage_unavailable_error import ImageStorageUnavailableError
from app.catalog.application.invalid_image_upload_error import InvalidImageUploadError
from app.catalog.application.product_conflict_error import ProductConflictError
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.errors.image_storage_error import ImageStorageError
from app.catalog.domain.errors.too_many_images_error import TooManyImagesError
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.catalog.domain.interfaces.product_image_storage import ProductImageStorage
from app.catalog.domain.services.image_sniffer import sniff_image_type
from app.core.events.business_event_logger import BusinessEventLogger
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGES_PER_PRODUCT = 10


def _random_token() -> str:
    return secrets.token_hex(16)


class UploadProductImageUseCase:
    """Ajoute une image à un produit : le type vient du contenu, le nom est tiré au hasard.

    Tout refus (vide, trop lourde, type inconnu, produit absent ou archivé, trop d'images) survient
    avant l'écriture dans le bucket : aucun effet de bord.
    """

    def __init__(
        self,
        repository: AdminProductRepository,
        storage: ProductImageStorage,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
        key_factory: Callable[[], str] = _random_token,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._events = events
        self._pseudonymizer = pseudonymizer
        self._key_factory = key_factory

    def execute(self, operator_id: UUID, product_id: str, content: bytes) -> Product:
        if not content:
            raise InvalidImageUploadError("empty")
        if len(content) > MAX_IMAGE_BYTES:
            raise InvalidImageUploadError("too_large")
        image_type = sniff_image_type(content)
        if image_type is None:
            raise InvalidImageUploadError("unsupported_type")
        current = self._repository.get(product_id)
        if current is None:
            raise ProductNotFoundError
        if current.archived_at is not None:
            raise ProductConflictError("product_archived")
        if len(current.image_keys) >= MAX_IMAGES_PER_PRODUCT:
            raise ProductConflictError("too_many_images")
        key = f"{self._key_factory()}.{image_type.extension}"
        try:
            self._storage.store(key, content, image_type.content_type)
        except ImageStorageError:
            raise ImageStorageUnavailableError from None
        try:
            product = self._repository.append_image(product_id, key, MAX_IMAGES_PER_PRODUCT)
        except TooManyImagesError:
            raise ProductConflictError("too_many_images") from None
        if product is None:
            raise ProductNotFoundError
        self._events.log(
            admin_events.change(
                admin_events.IMAGE,
                self._pseudonymizer.pseudonymize(str(operator_id)),
                product,
                current.price_cents,
            )
        )
        return product
