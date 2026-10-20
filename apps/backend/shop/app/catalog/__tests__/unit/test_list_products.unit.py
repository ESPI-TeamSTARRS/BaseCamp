import pytest

from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.invalid_catalog_query_error import InvalidCatalogQueryError
from app.catalog.application.list_products import ListProductsUseCase
from app.catalog.domain.entities.product import Product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.domain.interfaces.product_repository import ProductRepository
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger


class FakeProductRepository(ProductRepository):
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


def _use_case(events: InMemoryBusinessEventLogger | None = None) -> ListProductsUseCase:
    products = [make_product(f"tente-{i}") for i in range(5)] + [
        make_product("sac-1", category=ProductCategory.SACS_A_DOS)
    ]
    return ListProductsUseCase(
        FakeProductRepository(products), events or InMemoryBusinessEventLogger()
    )


class TestListProducts:
    def test_returns_all_products_without_filter(self) -> None:
        page = _use_case().execute(category=None, page=1, page_size=20)

        assert page.total == 6
        assert len(page.items) == 6

    def test_filters_by_category(self) -> None:
        page = _use_case().execute(category="sacs-a-dos", page=1, page_size=20)

        assert [p.slug for p in page.items] == ["sac-1"]
        assert page.total == 1

    def test_paginates_and_keeps_the_total(self) -> None:
        page = _use_case().execute(category=None, page=2, page_size=4)

        assert [p.slug for p in page.items] == ["tente-4", "sac-1"]
        assert (page.page, page.page_size, page.total) == (2, 4, 6)

    def test_unknown_category_is_rejected_without_echoing_the_input(self) -> None:
        with pytest.raises(InvalidCatalogQueryError) as error:
            _use_case().execute(category="<script>alert(1)</script>", page=1, page_size=10)

        assert "script" not in str(error.value)

    @pytest.mark.parametrize(("page", "page_size"), [(0, 10), (1, 0), (1, 101), (-1, 10)])
    def test_invalid_pagination_is_rejected(self, page: int, page_size: int) -> None:
        with pytest.raises(InvalidCatalogQueryError):
            _use_case().execute(category=None, page=page, page_size=page_size)


class TestListProductsEvents:
    def test_a_listing_emits_catalog_products_listed(self) -> None:
        events = InMemoryBusinessEventLogger()

        _use_case(events).execute(category="sacs-a-dos", page=2, page_size=4)

        (event,) = events.events
        assert (event.event, event.outcome.value, event.reason) == (
            "catalog.products_listed",
            "success",
            None,
        )
        assert event.attributes == {"category": "sacs-a-dos", "page": 2, "page_size": 4, "total": 1}

    def test_a_listing_without_category_omits_it(self) -> None:
        events = InMemoryBusinessEventLogger()

        _use_case(events).execute(category=None, page=1, page_size=20)

        assert "category" not in events.events[0].attributes

    @pytest.mark.parametrize(
        ("category", "page", "page_size"),
        [("<script>x</script>", 1, 10), (None, 0, 10), (None, 1, 101)],
    )
    def test_a_rejected_query_emits_a_denied_event_without_the_input(
        self, category: str | None, page: int, page_size: int
    ) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(InvalidCatalogQueryError):
            _use_case(events).execute(category=category, page=page, page_size=page_size)

        (event,) = events.events
        assert (event.event, event.outcome.value, event.reason) == (
            "catalog.query_rejected",
            "denied",
            "invalid_query",
        )
        assert "script" not in repr(event)
