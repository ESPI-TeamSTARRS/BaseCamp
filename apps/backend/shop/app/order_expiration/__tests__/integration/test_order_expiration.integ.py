from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order.application.place_order import PlaceOrderUseCase
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order.infrastructure.repositories.sqlalchemy_order_unit_of_work import (
    SqlAlchemyOrderUnitOfWork,
)
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

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class _Shop:
    """Boutique réelle sur SQLite : commandes, réservations, paiement et expiration."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.events = InMemoryBusinessEventLogger()
        self.now = NOW
        self.place = PlaceOrderUseCase(
            lambda: SqlAlchemyOrderUnitOfWork(engine), self.events, FakePseudonymizer()
        )
        gateway = SimulatedPaymentGateway(engine)
        factory = lambda: SqlAlchemyPaymentUnitOfWork(engine)  # noqa: E731
        self.request_payment = RequestOrderPaymentUseCase(factory, gateway, self.events)
        self.confirm_payment = ConfirmOrderPaymentUseCase(factory, gateway, self.events)
        self.expire = ExpireUnpaidOrdersUseCase(
            lambda: SqlAlchemyExpirationUnitOfWork(engine),
            self.events,
            clock=lambda: self.now,
            ttl_minutes=30,
        )

    def order(self, key: str, quantity: int = 2) -> str:
        placed = self.place.execute(
            PlaceOrderCommand(
                idempotency_key=key,
                email="camille.martin@example.org",
                full_name="Camille Martin",
                address_line1="12 rue des Alpes",
                address_line2=None,
                postal_code="38000",
                city="Grenoble",
                country="FR",
                items=(("popote", quantity),),
            )
        )
        return placed.order.id

    def age(self, order_id: str, minutes: int) -> None:
        with Session(self.engine) as session:
            session.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(created_at=NOW - timedelta(minutes=minutes))
            )
            session.commit()

    def stock(self) -> int:
        with Session(self.engine) as session:
            return session.scalars(select(OrderProductModel.stock)).one()

    def status(self, order_id: str) -> str:
        with Session(self.engine) as session:
            return session.scalars(select(OrderModel.status).where(OrderModel.id == order_id)).one()


@pytest.fixture
def shop() -> Iterator[_Shop]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=10))
        session.commit()
    yield _Shop(engine)
    engine.dispose()


class TestOrderExpirationOnTheDatabase:
    def test_an_unpaid_order_older_than_the_delay_expires_and_returns_its_stock(
        self, shop: _Shop
    ) -> None:
        order_id = shop.order("cle-exp-0001", quantity=3)
        assert shop.stock() == 7
        shop.age(order_id, minutes=31)

        report = shop.expire.execute()

        assert (report.expired_orders, report.released_units) == (1, 3)
        assert shop.status(order_id) == "expired"
        assert shop.stock() == 10
        with Session(shop.engine) as session:
            assert session.scalars(select(StockReservationModel.status)).all() == ["released"]

    def test_running_twice_returns_the_stock_only_once(self, shop: _Shop) -> None:
        order_id = shop.order("cle-exp-0001", quantity=3)
        shop.age(order_id, minutes=31)

        shop.expire.execute()
        second = shop.expire.execute()

        assert second.expired_orders == 0
        assert shop.stock() == 10

    def test_recent_and_paid_orders_are_never_expired(self, shop: _Shop) -> None:
        recent = shop.order("cle-exp-recent", quantity=1)
        paid = shop.order("cle-exp-paid0", quantity=2)
        shop.request_payment.execute(paid)
        shop.confirm_payment.execute(paid, "pm_test_success")
        shop.age(recent, minutes=10)
        shop.age(paid, minutes=600)

        report = shop.expire.execute()

        assert report.expired_orders == 0
        assert (shop.status(recent), shop.status(paid)) == ("pending_payment", "paid")
        assert shop.stock() == 7

    def test_a_payment_received_after_expiry_is_rejected_with_409_semantics_and_logged(
        self, shop: _Shop
    ) -> None:
        order_id = shop.order("cle-exp-late0")
        shop.request_payment.execute(order_id)
        shop.age(order_id, minutes=45)
        shop.expire.execute()
        shop.events.events.clear()

        with pytest.raises(OrderNotPayableError) as error:
            shop.confirm_payment.execute(order_id, "pm_test_success")

        assert error.value.reason == "order_expired"
        assert shop.status(order_id) == "expired"
        assert shop.stock() == 10  # la réservation n'est pas reprise
        (logged,) = shop.events.events
        assert (logged.event, logged.reason) == ("order.payment_rejected", "order_expired")

    def test_an_expired_order_cannot_ask_for_a_new_payment(self, shop: _Shop) -> None:
        order_id = shop.order("cle-exp-late1")
        shop.age(order_id, minutes=45)
        shop.expire.execute()

        with pytest.raises(OrderNotPayableError):
            shop.request_payment.execute(order_id)
