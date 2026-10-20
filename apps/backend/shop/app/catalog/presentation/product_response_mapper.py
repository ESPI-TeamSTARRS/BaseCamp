from app.catalog.application.list_products import Product
from app.catalog.presentation.schemas.product_response import ProductResponse
from app.catalog.presentation.schemas.product_specs_response import ProductSpecsResponse


class ProductResponseMapper:
    """Entite du domaine vers reponse HTTP (les cles d'image deviennent des URLs publiques)."""

    def __init__(self, media_base_url: str) -> None:
        self._media_base_url = media_base_url.rstrip("/")

    def to_response(self, product: Product) -> ProductResponse:
        image_urls = [f"{self._media_base_url}/{key}" for key in product.image_keys]
        return ProductResponse(
            id=product.id,
            slug=product.slug,
            name=product.name,
            category=product.category.value,
            price_cents=product.price_cents,
            compare_at_price_cents=product.compare_at_price_cents,
            short_description=product.short_description,
            description=product.description,
            thumbnail_url=image_urls[0] if image_urls else None,
            image_urls=image_urls,
            specs=ProductSpecsResponse(**vars(product.specs)),
            rating_value=product.rating_value,
            rating_count=product.rating_count,
            availability=product.availability.value,
        )
