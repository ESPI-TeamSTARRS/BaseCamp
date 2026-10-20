from abc import ABC, abstractmethod

from app.catalog.domain.entities.product import Product


class ProductLookup(ABC):
    @abstractmethod
    def get_by_slug(self, slug: str) -> Product | None: ...
