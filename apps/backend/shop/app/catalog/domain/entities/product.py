from dataclasses import dataclass

from app.catalog.domain.enums.availability import Availability
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.value_objects.product_specs import ProductSpecs

LOW_STOCK_THRESHOLD = 5
MAX_RATING = 5.0


@dataclass(frozen=True)
class Product:
    """Produit du catalogue. Le prix est un entier en centimes d'euro (jamais un flottant)."""

    id: str
    slug: str
    name: str
    category: ProductCategory
    price_cents: int
    compare_at_price_cents: int | None
    short_description: str
    description: str
    image_keys: tuple[str, ...]
    specs: ProductSpecs
    stock: int
    rating_value: float
    rating_count: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Le nom du produit est obligatoire.")
        if self.price_cents <= 0:
            raise ValueError("Le prix doit etre strictement positif.")
        if self.stock < 0:
            raise ValueError("Le stock ne peut pas etre negatif.")
        if not 0 <= self.rating_value <= MAX_RATING:
            raise ValueError("La note doit etre comprise entre 0 et 5.")

    @property
    def availability(self) -> Availability:
        if self.stock == 0:
            return Availability.OUT_OF_STOCK
        if self.stock <= LOW_STOCK_THRESHOLD:
            return Availability.LOW_STOCK
        return Availability.IN_STOCK

    @property
    def thumbnail_key(self) -> str | None:
        return self.image_keys[0] if self.image_keys else None
