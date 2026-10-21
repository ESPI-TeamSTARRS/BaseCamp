from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order_tracking.infrastructure.repositories.sqlalchemy_tracked_order_reader import (
    SqlAlchemyTrackedOrderReader,
)

ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=5))
        session.add(
            OrderModel(
                id=ORDER_ID,
                number="BC-ABCDEFGHJK",
                status="paid",
                email="camille.martin@example.org",
                ship_full_name="Camille Martin",
                ship_line1="12 rue des Alpes",
                ship_postal_code="38000",
                ship_city="Grenoble",
                ship_country="FR",
                subtotal_cents=7800,
                shipping_cents=0,
                total_cents=7800,
                idempotency_key="cle-suivi-0001",
                request_fingerprint="f" * 64,
                created_at=datetime(2026, 10, 21, 9, 30, tzinfo=UTC),
            )
        )
        session.flush()
        session.add_all(
            [
                OrderLineModel(
                    order_id=ORDER_ID,
                    position=1,
                    product_id="popote",
                    product_name="Popote bis",
                    unit_price_cents=100,
                    quantity=1,
                ),
                OrderLineModel(
                    order_id=ORDER_ID,
                    position=0,
                    product_id="popote",
                    product_name="Popote",
                    unit_price_cents=3900,
                    quantity=2,
                ),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


class TestSqlAlchemyTrackedOrderReader:
    def test_reads_the_order_with_its_frozen_lines_in_order(self, engine: Engine) -> None:
        order = SqlAlchemyTrackedOrderReader(engine).find_by_number("BC-ABCDEFGHJK")

        assert order is not None
        assert (order.status, order.total_cents) == ("paid", 7800)
        assert [(line.name, line.unit_price_cents, line.quantity) for line in order.lines] == [
            ("Popote", 3900, 2),
            ("Popote bis", 100, 1),
        ]

    def test_an_unknown_number_is_none(self, engine: Engine) -> None:
        assert SqlAlchemyTrackedOrderReader(engine).find_by_number("BC-ZZZZZZZZZZ") is None

    def test_the_number_is_a_bound_parameter(self, engine: Engine) -> None:
        assert SqlAlchemyTrackedOrderReader(engine).find_by_number("' OR '1'='1") is None

    def test_found_and_unknown_numbers_cost_the_same_number_of_queries(
        self, engine: Engine
    ) -> None:
        statements: list[str] = []
        event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
        reader = SqlAlchemyTrackedOrderReader(engine)

        reader.find_by_number("BC-ABCDEFGHJK")
        found = len(statements)
        statements.clear()
        reader.find_by_number("BC-ZZZZZZZZZZ")

        assert len(statements) == found == 2
