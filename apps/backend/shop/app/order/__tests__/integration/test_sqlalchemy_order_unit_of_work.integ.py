from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order.application.insufficient_stock_error import InsufficientStockError
from app.order.application.place_order import PlaceOrderUseCase
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.domain.errors.duplicate_idempotency_key_error import DuplicateIdempotencyKeyError
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order.infrastructure.repositories.sqlalchemy_order_unit_of_work import (
    SqlAlchemyOrderUnitOfWork,
)


def _command(items: tuple[tuple[str, int], ...], key: str = "cle-sql-0001") -> PlaceOrderCommand:
    return PlaceOrderCommand(
        idempotency_key=key,
        email="camille.martin@example.org",
        full_name="Camille Martin",
        address_line1="12 rue des Alpes",
        address_line2="Batiment B",
        postal_code="38000",
        city="Grenoble",
        country="FR",
        items=items,
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON")
    )  # comme Postgres
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                OrderProductModel(id="tente", name="Tente", price_cents=32900, stock=3),
                OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=5),
            ]
        )
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def use_case(engine: Engine) -> PlaceOrderUseCase:
    return PlaceOrderUseCase(
        lambda: SqlAlchemyOrderUnitOfWork(engine),
        InMemoryBusinessEventLogger(),
        FakePseudonymizer(),
    )


def _stock(engine: Engine, product_id: str) -> int:
    with Session(engine) as session:
        return session.scalars(
            select(OrderProductModel.stock).where(OrderProductModel.id == product_id)
        ).one()


def _count(engine: Engine, model: type[OrderBase]) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


class TestSqlAlchemyOrderUnitOfWork:
    def test_persists_the_order_its_frozen_lines_and_the_reservations(
        self, engine: Engine, use_case: PlaceOrderUseCase
    ) -> None:
        placed = use_case.execute(_command((("tente", 1), ("popote", 2))))

        assert placed.created is True
        assert _stock(engine, "tente") == 2
        assert _stock(engine, "popote") == 3
        with Session(engine) as session:
            row = session.scalars(select(OrderModel)).one()
            assert row.number == placed.order.number
            assert row.status == "pending_payment"
            assert (row.subtotal_cents, row.shipping_cents, row.total_cents) == (40700, 0, 40700)
            assert row.ship_line2 == "Batiment B"
            lines = session.scalars(select(OrderLineModel)).all()
            assert {(line.product_id, line.unit_price_cents, line.quantity) for line in lines} == {
                ("tente", 32900, 1),
                ("popote", 3900, 2),
            }
            reserved = session.scalars(select(StockReservationModel)).all()
            assert {(r.product_id, r.quantity, r.status) for r in reserved} == {
                ("tente", 1, "reserved"),
                ("popote", 2, "reserved"),
            }

    def test_the_stored_prices_do_not_follow_a_later_price_change(
        self, engine: Engine, use_case: PlaceOrderUseCase
    ) -> None:
        use_case.execute(_command((("popote", 1),)))
        with Session(engine) as session:
            product = session.get_one(OrderProductModel, "popote")
            product.price_cents = 9999
            session.commit()

        replay = use_case.execute(_command((("popote", 1),)))

        assert replay.created is False
        assert replay.order.lines[0].unit_price_cents == 3900
        assert replay.order.total_cents == 3900 + 590

    def test_replaying_the_key_reads_the_same_order_without_a_second_reservation(
        self, engine: Engine, use_case: PlaceOrderUseCase
    ) -> None:
        first = use_case.execute(_command((("popote", 2),)))
        second = use_case.execute(_command((("popote", 2),)))

        assert second.created is False
        assert second.order.id == first.order.id
        assert second.order.lines == first.order.lines
        assert second.order.address == first.order.address
        assert second.order.total_cents == first.order.total_cents
        assert _count(engine, OrderModel) == 1
        assert _stock(engine, "popote") == 3

    def test_insufficient_stock_leaves_the_database_untouched(
        self, engine: Engine, use_case: PlaceOrderUseCase
    ) -> None:
        with pytest.raises(InsufficientStockError):
            use_case.execute(_command((("popote", 1), ("tente", 4))))

        assert _stock(engine, "popote") == 5
        assert _stock(engine, "tente") == 3
        assert _count(engine, OrderModel) == 0
        assert _count(engine, StockReservationModel) == 0

    def test_a_duplicate_key_raises_the_domain_error(self, engine: Engine) -> None:
        first = PlaceOrderUseCase(
            lambda: SqlAlchemyOrderUnitOfWork(engine),
            InMemoryBusinessEventLogger(),
            FakePseudonymizer(),
        )
        order = first.execute(_command((("popote", 1),))).order

        with SqlAlchemyOrderUnitOfWork(engine) as uow, pytest.raises(DuplicateIdempotencyKeyError):
            uow.orders.add(
                type(order)(
                    id="autre-id",
                    number="BC-AUTRE00001",
                    status=order.status,
                    email=order.email,
                    address=order.address,
                    lines=order.lines,
                    idempotency_key=order.idempotency_key,
                    request_fingerprint=order.request_fingerprint,
                    created_at=order.created_at,
                )
            )
            uow.commit()
