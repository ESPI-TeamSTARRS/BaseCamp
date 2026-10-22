from dataclasses import asdict

from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.value_objects.product_specs import ProductSpecs
from app.catalog.infrastructure.models.product_model import ProductModel


class ProductMapper:
    @staticmethod
    def to_entity(model: ProductModel) -> Product:
        return Product(
            id=model.id,
            slug=model.slug,
            name=model.name,
            category=ProductCategory(model.category),
            price_cents=model.price_cents,
            compare_at_price_cents=model.compare_at_price_cents,
            short_description=model.short_description,
            description=model.description,
            image_keys=tuple(model.images),
            specs=ProductSpecs(**model.specs),
            stock=model.stock,
            rating_value=float(model.rating_value),
            rating_count=model.rating_count,
            version=model.version,
            archived_at=model.archived_at,
        )

    @staticmethod
    def to_model(product: Product) -> ProductModel:
        return ProductModel(
            id=product.id,
            slug=product.slug,
            name=product.name,
            category=product.category.value,
            price_cents=product.price_cents,
            compare_at_price_cents=product.compare_at_price_cents,
            short_description=product.short_description,
            description=product.description,
            images=list(product.image_keys),
            specs={k: v for k, v in asdict(product.specs).items() if v is not None},
            stock=product.stock,
            rating_value=product.rating_value,
            rating_count=product.rating_count,
            version=product.version,
            archived_at=product.archived_at,
        )
