from abc import ABC, abstractmethod
from datetime import datetime

from app.catalog.domain.entities.product import Product


class AdminProductRepository(ABC):
    """Écritures et lectures complètes (archivés compris) réservées à l'administration."""

    @abstractmethod
    def list_products(self, include_archived: bool, limit: int, offset: int) -> list[Product]: ...

    @abstractmethod
    def count(self, include_archived: bool) -> int: ...

    @abstractmethod
    def get(self, product_id: str) -> Product | None: ...

    @abstractmethod
    def add(self, product: Product) -> None:
        """Insère le produit; lève DuplicateProductError si l'identifiant ou le slug existe."""

    @abstractmethod
    def update(self, product: Product, expected_version: int) -> Product | None:
        """Enregistre si la version stockée vaut `expected_version` (puis l'incrémente); sinon None."""

    @abstractmethod
    def archive(self, product_id: str, at: datetime) -> Product | None:
        """Archive (soft delete), idempotent; None si le produit n'existe pas."""

    @abstractmethod
    def append_image(self, product_id: str, key: str, max_images: int) -> Product | None:
        """Ajoute la clé d'image (version incrémentée); lève TooManyImagesError; None si inconnu."""
