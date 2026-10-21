from typing import Any

from httpx import ASGITransport, AsyncClient

from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.get_product import GetProductUseCase
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.product_lookup import ProductLookup
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.main import create_app


class InMemoryProductLookup(ProductLookup):
    def __init__(self, products: list[Product]) -> None:
        self._by_slug = {p.slug: p for p in products}

    def get_by_slug(self, slug: str) -> Product | None:
        return self._by_slug.get(slug)


async def _get(path: str) -> tuple[int, Any]:
    application = create_app()
    application.state.get_product_use_case = GetProductUseCase(
        InMemoryProductLookup([make_product("tente-a", stock=3)]), InMemoryBusinessEventLogger()
    )
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        response = await client.get(path)
    return response.status_code, response.json()


class TestProductDetailRouter:
    async def test_returns_the_full_product_sheet(self) -> None:
        status_code, body = await _get("/products/tente-a")

        assert status_code == 200
        assert body["slug"] == "tente-a"
        assert body["description"] == "Description detaillee"
        assert body["specs"]["weight_grams"] == 1200
        assert body["specs"]["material"] == "Nylon"
        assert body["image_urls"] == ["/media/tente-a-1.svg"]
        assert (body["rating_value"], body["rating_count"]) == (4.5, 12)
        assert body["availability"] == "low_stock"
        assert body["price_cents"] == 12900

    async def test_unknown_slug_returns_a_generic_404_without_the_input(self) -> None:
        status_code, body = await _get("/products/zz-evil-zz")

        assert status_code == 404
        assert body == {"detail": "Produit introuvable."}
