"""Concurrence réelle sur Postgres : un événement ou une commande ne se confirme qu'une fois (ignoré sans Postgres)."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.payment_confirmation.__tests__.fakes import (
    NOW,
    ORDER_ID,
    ORDER_NUMBER,
    REFERENCE,
    SECRET,
    TOTAL_CENTS,
    event_body,
    sign,
)
from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)
from app.payment_confirmation.infrastructure.models.payment_webhook_event_model import (
    PaymentWebhookEventModel,
)
from app.payment_confirmation.infrastructure.repositories.sqlalchemy_confirmation_unit_of_work import (
    SqlAlchemyConfirmationUnitOfWork,
)
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel

POSTGRES_URL = os.environ.get("APP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="definir APP_TEST_POSTGRES_URL")

CONTENDERS = 6


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Schéma jetable propre au test : une base existante n'est jamais modifiée."""
    assert POSTGRES_URL is not None
    schema = f"test_hook_{uuid.uuid4().hex[:12]}"
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
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=8))
        session.add(
            OrderModel(
                id=ORDER_ID,
                number=ORDER_NUMBER,
                status="pending_payment",
                email="camille.martin@example.org",
                ship_full_name="Camille Martin",
                ship_line1="12 rue des Alpes",
                ship_postal_code="38000",
                ship_city="Grenoble",
                ship_country="FR",
                subtotal_cents=3900,
                shipping_cents=590,
                total_cents=TOTAL_CENTS,
                idempotency_key="cle-hook-0001",
                request_fingerprint="f" * 64,
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(
            PaymentAttemptModel(
                id="a1111111-6c52-4d3b-8a52-1d6f7a9b2c10",
                order_id=ORDER_ID,
                number=1,
                reference=REFERENCE,
                intent_id="pi-1",
                status="requires_confirmation",
                created_at=datetime.now(UTC),
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


def _use_case(engine: Engine) -> ReceivePaymentWebhookUseCase:
    return ReceivePaymentWebhookUseCase(
        lambda: SqlAlchemyConfirmationUnitOfWork(engine),
        WebhookSignatureVerifier((SECRET,), 300, lambda: NOW),
        InMemoryBusinessEventLogger(),
    )


def _receive(use_case: ReceivePaymentWebhookUseCase, event_id: str) -> WebhookOutcome:
    body = event_body(id=event_id)
    return use_case.execute(body, sign(body), event_id).outcome


class TestWebhookConcurrency:
    def test_the_same_event_delivered_in_parallel_is_applied_exactly_once(
        self, engine: Engine
    ) -> None:
        use_case = _use_case(engine)

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            outcomes = list(pool.map(lambda _: _receive(use_case, "evt-same"), range(CONTENDERS)))

        assert outcomes.count(WebhookOutcome.APPLIED) == 1
        assert outcomes.count(WebhookOutcome.REPLAYED) == CONTENDERS - 1
        self._assert_confirmed_once(engine, events=1)

    def test_different_events_for_the_same_order_confirm_it_exactly_once(
        self, engine: Engine
    ) -> None:
        use_case = _use_case(engine)

        with ThreadPoolExecutor(max_workers=CONTENDERS) as pool:
            outcomes = list(pool.map(lambda i: _receive(use_case, f"evt-{i}"), range(CONTENDERS)))

        assert outcomes.count(WebhookOutcome.APPLIED) == 1
        assert outcomes.count(WebhookOutcome.IGNORED) == CONTENDERS - 1
        self._assert_confirmed_once(engine, events=CONTENDERS)

    @staticmethod
    def _assert_confirmed_once(engine: Engine, events: int) -> None:
        with Session(engine) as session:
            assert session.scalars(select(OrderModel.status)).one() == "paid"
            assert session.scalars(select(StockReservationModel.status)).all() == ["committed"]
            assert session.scalars(select(PaymentAttemptModel.status)).one() == "succeeded"
            assert session.scalars(select(func.count(PaymentWebhookEventModel.id))).one() == events
            confirmed = session.scalars(
                select(func.count(PaymentWebhookEventModel.id)).where(
                    PaymentWebhookEventModel.paid_order_id == ORDER_ID
                )
            ).one()
            assert confirmed == 1
