from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cart.infrastructure.repositories.sqlalchemy_cart_product_reader import (
    SqlAlchemyCartProductReader,
)
from app.catalog.__tests__.product_factory import make_product
from app.catalog.infrastructure.mappers.product_mapper import ProductMapper
from app.catalog.infrastructure.models.base import CatalogBase


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    CatalogBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ProductMapper.to_model(make_product("tente-a", stock=7, price_cents=32900)))
        session.add(ProductMapper.to_model(make_product("tente-b", stock=0, price_cents=1500)))
        session.commit()
    yield engine
    engine.dispose()


class TestSqlAlchemyCartProductReader:
    def test_reads_price_and_stock_from_the_products_table(self, engine: Engine) -> None:
        products = SqlAlchemyCartProductReader(engine).find_by_ids(["id-tente-a", "id-tente-b"])

        by_id = {p.id: p for p in products}
        assert by_id["id-tente-a"].price_cents == 32900
        assert by_id["id-tente-a"].stock == 7
        assert by_id["id-tente-b"].stock == 0

    def test_ignores_unknown_ids(self, engine: Engine) -> None:
        products = SqlAlchemyCartProductReader(engine).find_by_ids(["id-tente-a", "inconnu"])

        assert [p.id for p in products] == ["id-tente-a"]

    def test_ids_are_bound_parameters(self, engine: Engine) -> None:
        assert SqlAlchemyCartProductReader(engine).find_by_ids(["' OR '1'='1"]) == []
