from abc import ABC, abstractmethod

from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory


class ProductRepository(ABC):
    @abstractmethod
    def list_products(
        self, category: ProductCategory | None, limit: int, offset: int
    ) -> list[Product]: ...

    @abstractmethod
    def count(self, category: ProductCategory | None) -> int: ...
