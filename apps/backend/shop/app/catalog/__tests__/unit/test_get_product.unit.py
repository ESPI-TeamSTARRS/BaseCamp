import pytest

from app.catalog.__tests__.product_factory import make_product
from app.catalog.application.get_product import GetProductUseCase
from app.catalog.application.product_not_found_error import ProductNotFoundError
from app.catalog.domain.entities.product import Product
from app.catalog.domain.interfaces.product_lookup import ProductLookup
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger


class FakeProductLookup(ProductLookup):
    def __init__(self, products: list[Product]) -> None:
        self._by_slug = {p.slug: p for p in products}

    def get_by_slug(self, slug: str) -> Product | None:
        return self._by_slug.get(slug)


class TestGetProduct:
    def test_returns_the_product_for_an_existing_slug(self) -> None:
        use_case = GetProductUseCase(
            FakeProductLookup([make_product("tente-a")]), InMemoryBusinessEventLogger()
        )

        assert use_case.execute("tente-a").slug == "tente-a"

    def test_unknown_slug_raises_a_generic_error_without_the_input(self) -> None:
        use_case = GetProductUseCase(
            FakeProductLookup([make_product("tente-a")]), InMemoryBusinessEventLogger()
        )

        with pytest.raises(ProductNotFoundError) as error:
            use_case.execute("<script>zz-evil-zz</script>")

        assert "zz-evil-zz" not in str(error.value)


class TestGetProductEvents:
    def test_a_view_emits_catalog_product_viewed_with_the_product_id(self) -> None:
        events = InMemoryBusinessEventLogger()

        GetProductUseCase(FakeProductLookup([make_product("tente-a")]), events).execute("tente-a")

        (event,) = events.events
        assert (event.event, event.outcome.value) == ("catalog.product_viewed", "success")
        assert (event.resource_type, event.resource_id) == ("product", "id-tente-a")

    def test_an_unknown_slug_emits_a_denied_event_without_the_slug(self) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(ProductNotFoundError):
            GetProductUseCase(FakeProductLookup([]), events).execute("<script>zz-evil-zz</script>")

        (event,) = events.events
        assert (event.event, event.outcome.value, event.reason) == (
            "catalog.product_not_found",
            "denied",
            "product_not_found",
        )
        assert event.resource_type == "product" and event.resource_id is None
        assert "evil" not in repr(event)
