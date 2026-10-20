from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.catalog.__tests__.product_factory import make_product
from app.catalog.domain.enums.product_category import ProductCategory
from app.catalog.infrastructure.mappers.product_mapper import ProductMapper
from app.catalog.infrastructure.models.base import CatalogBase
from app.catalog.infrastructure.repositories.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    CatalogBase.metadata.create_all(engine)
    with Session(engine) as session:
        for slug, category in [
            ("tente-a", ProductCategory.TENTES),
            ("tente-b", ProductCategory.TENTES),
            ("sac-a", ProductCategory.SACS_A_DOS),
        ]:
            session.add(ProductMapper.to_model(make_product(slug, category)))
        session.commit()
    yield engine
    engine.dispose()


class TestSqlAlchemyProductRepository:
    def test_lists_products_ordered_by_name(self, engine: Engine) -> None:
        products = SqlAlchemyProductRepository(engine).list_products(None, limit=10, offset=0)

        assert [p.slug for p in products] == ["sac-a", "tente-a", "tente-b"]

    def test_filters_by_category(self, engine: Engine) -> None:
        repository = SqlAlchemyProductRepository(engine)

        products = repository.list_products(ProductCategory.TENTES, limit=10, offset=0)

        assert [p.slug for p in products] == ["tente-a", "tente-b"]
        assert repository.count(ProductCategory.TENTES) == 2
        assert repository.count(None) == 3

    def test_applies_limit_and_offset(self, engine: Engine) -> None:
        products = SqlAlchemyProductRepository(engine).list_products(None, limit=1, offset=1)

        assert [p.slug for p in products] == ["tente-a"]

    def test_maps_the_row_back_to_a_domain_entity(self, engine: Engine) -> None:
        product = SqlAlchemyProductRepository(engine).list_products(None, 10, 0)[0]

        assert product.price_cents == 12900
        assert product.category is ProductCategory.SACS_A_DOS
        assert product.specs.weight_grams == 1200
        assert product.image_keys == ("sac-a-1.svg",)
