from dataclasses import asdict

from app.catalog.application.list_products import Product
from app.catalog.presentation.schemas.admin_product_response import AdminProductResponse


class AdminProductResponseMapper:
    """Réponse d'administration : version et archivage inclus, URLs d'images servies par `/media`."""

    def __init__(self, media_base_url: str) -> None:
        self._media_base_url = media_base_url.rstrip("/")

    def to_response(self, product: Product) -> AdminProductResponse:
        return AdminProductResponse(
            id=product.id,
            slug=product.slug,
            name=product.name,
            category=product.category.value,
            price_cents=product.price_cents,
            compare_at_price_cents=product.compare_at_price_cents,
            short_description=product.short_description,
            description=product.description,
            specs={k: v for k, v in asdict(product.specs).items() if v is not None},
            stock=product.stock,
            availability=product.availability.value,
            image_keys=list(product.image_keys),
            image_urls=[f"{self._media_base_url}/{key}" for key in product.image_keys],
            version=product.version,
            archived_at=product.archived_at,
        )
