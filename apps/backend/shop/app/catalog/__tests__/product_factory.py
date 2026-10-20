"""Fabrique de produits pour les tests du catalogue (pas un test)."""

from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.value_objects.product_specs import ProductSpecs


def make_product(
    slug: str = "tente-test",
    category: ProductCategory = ProductCategory.TENTES,
    stock: int = 10,
    price_cents: int = 12900,
) -> Product:
    return Product(
        id=f"id-{slug}",
        slug=slug,
        name=f"Produit {slug}",
        category=category,
        price_cents=price_cents,
        compare_at_price_cents=None,
        short_description="Resume",
        description="Description detaillee",
        image_keys=(f"{slug}-1.svg",),
        specs=ProductSpecs(weight_grams=1200, material="Nylon"),
        stock=stock,
        rating_value=4.5,
        rating_count=12,
    )
