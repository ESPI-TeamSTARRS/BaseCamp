from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.order.domain.enums.order_status import OrderStatus
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.payment_request.domain.entities.payment_attempt import PaymentAttempt
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_unit_of_work import (
    SqlAlchemyPaymentUnitOfWork,
)

ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"


def _order_row(status: str = "pending_payment") -> OrderModel:
    return OrderModel(
        id=ORDER_ID,
        number="BC-ABCDEFGHJK",
        status=status,
        email="camille.martin@example.org",
        ship_full_name="Camille Martin",
        ship_line1="12 rue des Alpes",
        ship_line2=None,
        ship_postal_code="38000",
        ship_city="Grenoble",
        ship_country="FR",
        subtotal_cents=3900,
        shipping_cents=590,
        total_cents=4490,
        idempotency_key="cle-sql-0001",
        request_fingerprint="f" * 64,
        created_at=datetime.now(UTC),
    )


def _attempt(number: int = 1, status: str = "requires_confirmation") -> PaymentAttempt:
    return PaymentAttempt(
        id=f"att-{number}",
        order_id=ORDER_ID,
        number=number,
        reference=f"BC-ABCDEFGHJK-{number}",
        intent_id=f"pi-{number}",
        status=status,
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=5))
        session.add(_order_row())
        session.commit()
    yield engine
    engine.dispose()


def _order_status(engine: Engine) -> str:
    with Session(engine) as session:
        return session.scalars(select(OrderModel.status)).one()


class TestSqlAlchemyPaymentUnitOfWork:
    def test_reads_the_stored_total_and_status_of_the_order(self, engine: Engine) -> None:
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            order = uow.orders.find_for_update(ORDER_ID)

        assert order is not None
        assert (order.number, order.status, order.total_cents) == (
            "BC-ABCDEFGHJK",
            OrderStatus.PENDING_PAYMENT,
            4490,
        )

    def test_an_unknown_order_is_none(self, engine: Engine) -> None:
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            assert uow.orders.find_for_update("inconnue") is None

    def test_attempts_are_listed_in_order_and_their_status_can_change(self, engine: Engine) -> None:
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            uow.attempts.add(_attempt(2))
            uow.attempts.add(_attempt(1))
            uow.commit()
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            uow.attempts.set_status("att-1", "failed")
            uow.commit()

        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            attempts = uow.attempts.list_for_order(ORDER_ID)
        assert [(a.number, a.status) for a in attempts] == [
            (1, "failed"),
            (2, "requires_confirmation"),
        ]

    def test_mark_paid_is_written_at_commit(self, engine: Engine) -> None:
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            uow.orders.mark_paid(ORDER_ID)
            uow.commit()

        assert _order_status(engine) == "paid"

    def test_nothing_is_written_without_a_commit(self, engine: Engine) -> None:
        with SqlAlchemyPaymentUnitOfWork(engine) as uow:
            uow.orders.mark_paid(ORDER_ID)
            uow.attempts.add(_attempt())

        assert _order_status(engine) == "pending_payment"
        with Session(engine) as session:
            assert session.scalars(select(PaymentAttemptModel)).all() == []
