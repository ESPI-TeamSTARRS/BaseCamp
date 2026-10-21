"""Concurrence reelle sur Postgres (SELECT ... FOR UPDATE) : ignore sans APP_TEST_POSTGRES_URL.

SQLite ne verrouille pas les lignes : seul un vrai Postgres prouve l'invariant de stock.
"""

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order.application.insufficient_stock_error import InsufficientStockError
from app.order.application.place_order import PlaceOrderUseCase
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.application.placed_order import PlacedOrder
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order.infrastructure.repositories.sqlalchemy_order_unit_of_work import (
    SqlAlchemyOrderUnitOfWork,
)

POSTGRES_URL = os.environ.get("APP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="definir APP_TEST_POSTGRES_URL")

CONTENDERS = 8


def _command(key: str, quantity: int = 1) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        idempotency_key=key,
        email="camille.martin@example.org",
        full_name="Camille Martin",
        address_line1="12 rue des Alpes",
        address_line2=None,
        postal_code="38000",
        city="Grenoble",
        country="FR",
        items=(("derniere-piece", quantity),),
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_size=CONTENDERS + 2)
    OrderBase.metadata.drop_all(engine)
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="derniere-piece", name="Rare", price_cents=2000, stock=1))
        session.commit()
    yield engine
    OrderBase.metadata.drop_all(engine)
    engine.dispose()


def _run_concurrently(engine: Engine, commands: list[PlaceOrderCommand]) -> list[object]:
    use_case = PlaceOrderUseCase(
        lambda: SqlAlchemyOrderUnitOfWork(engine),
        InMemoryBusinessEventLogger(),
        FakePseudonymizer(),
    )

    def attempt(command: PlaceOrderCommand) -> object:
        try:
            return use_case.execute(command)
        except InsufficientStockError as error:
            return error

    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        futures = [pool.submit(attempt, command) for command in commands]
        return [future.result() for future in futures]


def _scalar(engine: Engine, statement: Callable[[], object]) -> int:
    with Session(engine) as session:
        return int(session.scalar(statement()) or 0)  # type: ignore[call-overload]


class TestOrderConcurrency:
    def test_two_orders_on_the_last_piece_only_one_succeeds(self, engine: Engine) -> None:
        results = _run_concurrently(engine, [_command("cle-A-00001"), _command("cle-B-00001")])

        winners = [r for r in results if isinstance(r, PlacedOrder)]
        losers = [r for r in results if isinstance(r, InsufficientStockError)]
        assert len(winners) == 1
        assert len(losers) == 1
        assert _scalar(engine, lambda: select(OrderProductModel.stock)) == 0

    def test_many_contenders_never_make_the_stock_negative(self, engine: Engine) -> None:
        commands = [_command(f"cle-{i:04d}-abcd") for i in range(CONTENDERS)]

        results = _run_concurrently(engine, commands)

        assert sum(isinstance(r, PlacedOrder) for r in results) == 1
        assert sum(isinstance(r, InsufficientStockError) for r in results) == CONTENDERS - 1
        assert _scalar(engine, lambda: select(OrderProductModel.stock)) == 0
        assert _scalar(engine, lambda: select(func.count()).select_from(OrderModel)) == 1
        assert _scalar(engine, lambda: select(func.count()).select_from(StockReservationModel)) == 1

    def test_the_same_key_sent_in_parallel_creates_a_single_order(self, engine: Engine) -> None:
        results = _run_concurrently(engine, [_command("cle-meme-0001")] * CONTENDERS)

        placed = [r for r in results if isinstance(r, PlacedOrder)]
        assert len(placed) == CONTENDERS  # aucun 409 : les rejeux renvoient la meme commande
        assert sum(p.created for p in placed) == 1
        assert len({p.order.id for p in placed}) == 1
        assert _scalar(engine, lambda: select(func.count()).select_from(OrderModel)) == 1
        assert _scalar(engine, lambda: select(OrderProductModel.stock)) == 0
