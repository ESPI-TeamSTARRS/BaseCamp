from dataclasses import dataclass

from app.catalog.domain.entities.product import Product


@dataclass(frozen=True)
class ProductPage:
    items: tuple[Product, ...]
    page: int
    page_size: int
    total: int
