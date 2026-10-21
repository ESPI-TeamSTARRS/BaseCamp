"""Concurrence réelle sur Postgres : une commande ne se paie qu'une fois (ignoré sans Postgres)."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.payment_request.application.confirm_order_payment import ConfirmOrderPaymentUseCase
from app.payment_request.application.order_not_payable_error import OrderNotPayableError
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.infrastructure.gateways.simulated_payment_gateway import (
    SimulatedPaymentGateway,
)
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_unit_of_work import (
    SqlAlchemyPaymentUnitOfWork,
)

POSTGRES_URL = os.environ.get("APP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="definir APP_TEST_POSTGRES_URL")

ORDER_ID = "0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10"
CONTENDERS = 6


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Schéma jetable propre au test : une base existante n'est jamais modifiée."""
    assert POSTGRES_URL is not None
    schema = f"test_pay_{uuid.uuid4().hex[:12]}"
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        POSTGRES_URL,
        pool_size=CONTENDERS + 2,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
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
                subtotal_cents=3900,
                shipping_cents=590,
                total_cents=4490,
                idempotency_key="cle-pay-0001",
                request_fingerprint="f" * 64,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def _outcome(use_case: ConfirmOrderPaymentUseCase) -> str:
    try:
        return use_case.execute(ORDER_ID, "pm_test_success").payment_status
    except OrderNotPayableError as error:
        return error.reason


class TestPaymentConcurrency:
    def test_parallel_confirmations_pay_the_order_exactly_once(self, engine: Engine) -> None:
        events = InMemoryBusinessEventLogger()
        gateway = SimulatedPaymentGateway(engine)
        factory = lambda: SqlAlchemyPaymentUnitOfWork(engine)  # noqa: E731
        RequestOrderPaymentUseCase(factory, gateway, events).execute(ORDER_ID)
        confirm = ConfirmOrderPaymentUseCase(factory, gateway, events)

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            outcomes = list(pool.map(lambda _: _outcome(confirm), range(CONTENDERS)))

        assert outcomes.count("succeeded") == 1
        assert outcomes.count("order_already_paid") == CONTENDERS - 1
        assert [e.event for e in events.events].count("order.paid") == 1
        with Session(engine) as session:
            assert session.scalars(select(OrderModel.status)).one() == "paid"
            assert session.scalars(select(PaymentAttemptModel.status)).all() == ["succeeded"]

    def test_parallel_payment_requests_create_a_single_attempt(self, engine: Engine) -> None:
        events = InMemoryBusinessEventLogger()
        gateway = SimulatedPaymentGateway(engine)
        request = RequestOrderPaymentUseCase(
            lambda: SqlAlchemyPaymentUnitOfWork(engine), gateway, events
        )

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            payments = list(pool.map(lambda _: request.execute(ORDER_ID), range(CONTENDERS)))

        assert sum(p.created for p in payments) == 1
        assert len({p.intent.id for p in payments}) == 1
        with Session(engine) as session:
            assert len(session.scalars(select(PaymentAttemptModel)).all()) == 1
