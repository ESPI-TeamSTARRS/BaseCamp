"""Un produit archivé (soft delete) disparaît du catalogue, du panier et des nouvelles commandes, sans rien effacer."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cart.infrastructure.repositories.sqlalchemy_cart_product_reader import (
    SqlAlchemyCartProductReader,
)
from app.catalog.__tests__.product_factory import make_product
from app.catalog.infrastructure.mappers.product_mapper import ProductMapper
from app.catalog.infrastructure.models.base import CatalogBase
from app.catalog.infrastructure.models.product_model import ProductModel
from app.catalog.infrastructure.repositories.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_line_model import OrderLineModel  # noqa: F401
from app.order.infrastructure.models.order_model import OrderModel  # noqa: F401
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel  # noqa: F401
from app.order.infrastructure.repositories.sqlalchemy_stock_ledger import SqlAlchemyStockLedger

ARCHIVED_AT = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    CatalogBase.metadata.create_all(engine)
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ProductMapper.to_model(make_product("visible")))
        archived = ProductMapper.to_model(make_product("archive"))
        archived.archived_at = ARCHIVED_AT
        session.add(archived)
        session.commit()
    yield engine
    engine.dispose()


class TestArchivedProductsLeaveTheCustomerSide:
    def test_the_catalog_lists_counts_and_serves_only_visible_products(
        self, engine: Engine
    ) -> None:
        repository = SqlAlchemyProductRepository(engine)

        assert [p.slug for p in repository.list_products(None, 10, 0)] == ["visible"]
        assert repository.count(None) == 1
        assert repository.get_by_slug("visible") is not None
        assert repository.get_by_slug("archive") is None

    def test_the_cart_quote_ignores_an_archived_product(self, engine: Engine) -> None:
        found = SqlAlchemyCartProductReader(engine).find_by_ids(["id-visible", "id-archive"])

        assert [p.id for p in found] == ["id-visible"]

    def test_a_new_order_cannot_lock_an_archived_product(self, engine: Engine) -> None:
        with Session(engine) as session:
            items = SqlAlchemyStockLedger(session).lock_items(["id-visible", "id-archive"])

        assert [i.product_id for i in items] == ["id-visible"]

    def test_nothing_is_deleted_and_the_row_stays_readable_for_past_orders(
        self, engine: Engine
    ) -> None:
        with Session(engine) as session:
            row = session.scalars(select(ProductModel).where(ProductModel.id == "id-archive")).one()

            assert row.archived_at is not None
            assert row.name  # une commande passée garde son nom figé et la ligne reste présente


class TestStockChangesBumpTheVersion:
    def test_reserving_stock_increments_the_version_so_a_stale_edit_is_refused(
        self, engine: Engine
    ) -> None:
        with Session(engine) as session:
            before = session.scalars(
                select(OrderProductModel.version).where(OrderProductModel.id == "id-visible")
            ).one()

            SqlAlchemyStockLedger(session).reserve("order-1", "id-visible", 2)
            session.flush()
            after = session.scalars(
                select(OrderProductModel.version).where(OrderProductModel.id == "id-visible")
            ).one()

        assert after == before + 1
