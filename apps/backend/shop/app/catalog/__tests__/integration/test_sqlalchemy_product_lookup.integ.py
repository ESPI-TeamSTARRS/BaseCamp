from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.catalog.__tests__.product_factory import make_product
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
        session.add(ProductMapper.to_model(make_product("tente-a")))
        session.commit()
    yield engine
    engine.dispose()


class TestSqlAlchemyProductLookup:
    def test_finds_a_product_by_slug_with_its_details(self, engine: Engine) -> None:
        product = SqlAlchemyProductRepository(engine).get_by_slug("tente-a")

        assert product is not None
        assert product.description == "Description detaillee"
        assert product.specs.weight_grams == 1200
        assert product.image_keys == ("tente-a-1.svg",)

    def test_returns_none_for_an_unknown_slug(self, engine: Engine) -> None:
        assert SqlAlchemyProductRepository(engine).get_by_slug("inconnu") is None

    def test_slug_is_matched_as_a_literal_value(self, engine: Engine) -> None:
        assert SqlAlchemyProductRepository(engine).get_by_slug("' OR '1'='1") is None
