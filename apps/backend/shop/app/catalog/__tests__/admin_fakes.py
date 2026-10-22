"""Doublures de l'administration du catalogue : dépôt en mémoire et stockage d'images en mémoire."""

from dataclasses import replace
from datetime import datetime

from app.catalog.domain.entities.product import Product
from app.catalog.domain.errors.duplicate_product_error import DuplicateProductError
from app.catalog.domain.errors.image_storage_error import ImageStorageError
from app.catalog.domain.errors.too_many_images_error import TooManyImagesError
from app.catalog.domain.interfaces.admin_product_repository import AdminProductRepository
from app.catalog.domain.interfaces.product_image_storage import ProductImageStorage

OPERATOR_ID = "5a1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


class InMemoryAdminProducts(AdminProductRepository):
    def __init__(self, *products: Product) -> None:
        self.products = {p.id: p for p in products}

    def list_products(
        self, include_archived: bool, limit: int, offset: int, search: str | None = None
    ) -> list[Product]:
        rows = self._rows(include_archived, search)
        return sorted(rows, key=lambda p: (p.name, p.id))[offset : offset + limit]

    def count(self, include_archived: bool, search: str | None = None) -> int:
        return len(self._rows(include_archived, search))

    def _rows(self, include_archived: bool, search: str | None = None) -> list[Product]:
        return [
            p
            for p in self.products.values()
            if (include_archived or p.archived_at is None)
            and (not search or search.lower() in p.name.lower())
        ]

    def get(self, product_id: str) -> Product | None:
        return self.products.get(product_id)

    def add(self, product: Product) -> None:
        if product.id in self.products or any(
            p.slug == product.slug for p in self.products.values()
        ):
            raise DuplicateProductError
        self.products[product.id] = product

    def update(self, product: Product, expected_version: int) -> Product | None:
        current = self.products.get(product.id)
        if current is None or current.version != expected_version or current.archived_at:
            return None
        saved = replace(product, version=current.version + 1)
        self.products[product.id] = saved
        return saved

    def archive(self, product_id: str, at: datetime) -> Product | None:
        current = self.products.get(product_id)
        if current is None:
            return None
        if current.archived_at is None:
            current = replace(current, archived_at=at, version=current.version + 1)
            self.products[product_id] = current
        return current

    def append_image(self, product_id: str, key: str, max_images: int) -> Product | None:
        current = self.products.get(product_id)
        if current is None:
            return None
        if len(current.image_keys) >= max_images:
            raise TooManyImagesError
        saved = replace(current, image_keys=(*current.image_keys, key), version=current.version + 1)
        self.products[product_id] = saved
        return saved


class InMemoryImageStorage(ProductImageStorage):
    def __init__(self, failing: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.failing = failing

    def store(self, key: str, content: bytes, content_type: str) -> None:
        if self.failing:
            raise ImageStorageError
        self.objects[key] = (content, content_type)
