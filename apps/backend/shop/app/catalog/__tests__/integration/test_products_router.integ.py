from typing import Any

from httpx import ASGITransport, AsyncClient

from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.interfaces.product_repository import ProductRepository
from app.main import create_app


class InMemoryProductRepository(ProductRepository):
    def __init__(self, products: list[Product]) -> None:
        self._products = products

    def list_products(
        self, category: ProductCategory | None, limit: int, offset: int
    ) -> list[Product]:
        return self._filter(category)[offset : offset + limit]

    def count(self, category: ProductCategory | None) -> int:
        return len(self._filter(category))

    def _filter(self, category: ProductCategory | None) -> list[Product]:
        return [p for p in self._products if category is None or p.category is category]


async def _get(path: str) -> tuple[int, Any]:
    products = [
        make_product("tente-a", stock=10),
        make_product("tente-b", stock=3),
        make_product("sac-a", ProductCategory.SACS_A_DOS, stock=0),
    ]
    application = create_app()
    application.state.list_products_use_case = ListProductsUseCase(
        InMemoryProductRepository(products)
    )
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        response = await client.get(path)
    return response.status_code, response.json()


class TestProductsRouter:
    async def test_lists_products_with_pagination_metadata(self) -> None:
        status_code, body = await _get("/products")

        assert status_code == 200
        assert (body["page"], body["page_size"], body["total"]) == (1, 12, 3)
        item = body["items"][0]
        assert {"id", "slug", "name", "category", "price_cents", "thumbnail_url"} <= item.keys()
        assert {"rating_value", "rating_count", "availability", "specs"} <= item.keys()

    async def test_exposes_integer_cents_thumbnail_url_and_availability(self) -> None:
        _, body = await _get("/products")

        by_slug = {item["slug"]: item for item in body["items"]}
        assert by_slug["tente-a"]["price_cents"] == 12900
        assert by_slug["tente-a"]["thumbnail_url"] == "/media/tente-a-1.svg"
        assert by_slug["tente-a"]["availability"] == "in_stock"
        assert by_slug["tente-b"]["availability"] == "low_stock"
        assert by_slug["sac-a"]["availability"] == "out_of_stock"

    async def test_never_exposes_the_raw_stock(self) -> None:
        _, body = await _get("/products")

        assert "stock" not in body["items"][0]

    async def test_filters_by_category(self) -> None:
        status_code, body = await _get("/products?category=tentes")

        assert status_code == 200
        assert {item["category"] for item in body["items"]} == {"tentes"}
        assert body["total"] == 2

    async def test_unknown_category_returns_422_without_echoing_the_input(self) -> None:
        status_code, body = await _get("/products?category=zz-evil-zz")

        assert status_code == 422
        assert "zz-evil-zz" not in str(body)

    async def test_invalid_pagination_returns_422_without_echoing_the_input(self) -> None:
        status_code, body = await _get("/products?page_size=zz-evil-zz")

        assert status_code == 422
        assert "zz-evil-zz" not in str(body)
