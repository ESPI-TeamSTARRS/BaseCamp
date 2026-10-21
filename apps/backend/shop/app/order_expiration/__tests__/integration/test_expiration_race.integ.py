"""Course expiration / paiement sur Postgres (verrous de ligne) : ignoré sans APP_TEST_POSTGRES_URL."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order_expiration.application.expire_unpaid_orders import ExpireUnpaidOrdersUseCase
from app.order_expiration.infrastructure.repositories.sqlalchemy_expiration_unit_of_work import (
    SqlAlchemyExpirationUnitOfWork,
)
from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.infrastructure.gateways.simulated_payment_gateway import (
    SimulatedPaymentGateway,
)
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_unit_of_work import (
    SqlAlchemyPaymentUnitOfWork,
)

POSTGRES_URL = os.environ.get("APP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="definir APP_TEST_POSTGRES_URL")

ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Schéma jetable propre au test : une base existante n'est jamais modifiée."""
    assert POSTGRES_URL is not None
    schema = f"test_exp_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        POSTGRES_URL, pool_size=6, connect_args={"options": f"-csearch_path={schema}"}
    )
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=3))
        session.add(
            OrderModel(
                id=ORDER_ID,
                number="BC-ABCDEFGHJK",
                status="pending_payment",
                email="camille.martin@example.org",
                ship_full_name="Camille Martin",
                ship_line1="12 rue des Alpes",
                ship_postal_code="38000",
                ship_city="Grenoble",
                ship_country="FR",
                subtotal_cents=7800,
                shipping_cents=0,
                total_cents=7800,
                idempotency_key="cle-race-0001",
                request_fingerprint="f" * 64,
                created_at=NOW - timedelta(hours=2),
            )
        )
        session.add(
            StockReservationModel(
                order_id=ORDER_ID, product_id="popote", quantity=2, status="reserved"
            )
        )
        session.commit()
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def _expire(engine: Engine) -> int:
    use_case = ExpireUnpaidOrdersUseCase(
        lambda: SqlAlchemyExpirationUnitOfWork(engine),
        InMemoryBusinessEventLogger(),
        clock=lambda: NOW,
        ttl_minutes=30,
    )
    return use_case.execute().expired_orders


def _state(engine: Engine) -> tuple[str, int]:
    with Session(engine) as session:
        status = session.scalars(select(OrderModel.status)).one()
        stock = session.scalars(select(OrderProductModel.stock)).one()
    return status, stock


class TestExpirationRace:
    def test_an_order_being_paid_is_skipped_then_stays_paid_with_its_stock(
        self, engine: Engine
    ) -> None:
        events = InMemoryBusinessEventLogger()
        gateway = SimulatedPaymentGateway(engine)
        factory = lambda: SqlAlchemyPaymentUnitOfWork(engine)  # noqa: E731
        RequestOrderPaymentUseCase(factory, gateway, events).execute(ORDER_ID)

        with SqlAlchemyPaymentUnitOfWork(engine) as paying:
            assert (
                paying.orders.find_for_update(ORDER_ID) is not None
            )  # verrou tenu par le paiement
            skipped = _expire(engine)  # ne doit ni bloquer ni expirer
            paying.orders.mark_paid(ORDER_ID)
            paying.commit()

        assert skipped == 0
        assert _expire(engine) == 0
        assert _state(engine) == ("paid", 3)

    def test_expiring_first_then_paying_is_rejected_and_the_stock_is_returned_once(
        self, engine: Engine
    ) -> None:
        events = InMemoryBusinessEventLogger()
        gateway = SimulatedPaymentGateway(engine)
        factory = lambda: SqlAlchemyPaymentUnitOfWork(engine)  # noqa: E731
        RequestOrderPaymentUseCase(factory, gateway, events).execute(ORDER_ID)

        assert _expire(engine) == 1
        with pytest.raises(OrderNotPayableError) as error:
            ConfirmOrderPaymentUseCase(factory, gateway, events).execute(
                ORDER_ID, "pm_test_success"
            )

        assert error.value.reason == "order_expired"
        assert _state(engine) == ("expired", 5)

    def test_parallel_expirations_release_the_stock_exactly_once(self, engine: Engine) -> None:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: _expire(engine), range(5)))

        assert sum(results) == 1
        assert _state(engine) == ("expired", 5)
