"""Confirmation par webhook sur la base réelle (SQLite) : commande, stock, tentative, mémoire des événements."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, event, select, update
from sqlalchemy.exc import IntegrityError
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
from app.payment_confirmation.__tests__.fakes import NOW, SECRET, event_body, sign
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
from app.payment_request.application.request_order_payment import RequestOrderPaymentUseCase
from app.payment_request.infrastructure.gateways.simulated_payment_gateway import (
    SimulatedPaymentGateway,
)
from app.payment_request.infrastructure.models.payment_attempt_model import PaymentAttemptModel
from app.payment_request.infrastructure.repositories.sqlalchemy_payment_unit_of_work import (
    SqlAlchemyPaymentUnitOfWork,
)

EMAIL = "camille.martin@example.org"
EVENT_1 = "0b6d4e0e-6a3f-4c58-9d8e-5f0f4d1d9a11"
EVENT_2 = "5c1c4b52-96a6-4d52-8f0b-6b0e1b2f7a33"


class _Shop:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.events = InMemoryBusinessEventLogger()
        place = PlaceOrderUseCase(
            lambda: SqlAlchemyOrderUnitOfWork(engine), self.events, FakePseudonymizer()
        )
        self._place = place
        self.request_payment = RequestOrderPaymentUseCase(
            lambda: SqlAlchemyPaymentUnitOfWork(engine),
            SimulatedPaymentGateway(engine),
            self.events,
        )
        self.receive = ReceivePaymentWebhookUseCase(
            lambda: SqlAlchemyConfirmationUnitOfWork(engine),
            WebhookSignatureVerifier((SECRET,), 300, lambda: NOW),
            self.events,
        )

    def pending_order(self, key: str = "cle-hook-0001", quantity: int = 2) -> tuple[str, str, int]:
        """Une commande en attente avec une tentative de paiement; renvoie (id, référence, total)."""
        placed = self._place.execute(
            PlaceOrderCommand(
                idempotency_key=key,
                email=EMAIL,
                full_name="Camille Martin",
                address_line1="12 rue des Alpes",
                address_line2=None,
                postal_code="38000",
                city="Grenoble",
                country="FR",
                items=(("popote", quantity),),
            )
        )
        self.request_payment.execute(placed.order.id)
        with Session(self.engine) as session:
            reference = session.scalars(
                select(PaymentAttemptModel.reference).where(
                    PaymentAttemptModel.order_id == placed.order.id
                )
            ).one()
        return placed.order.id, reference, placed.order.total_cents

    def webhook(self, reference: str, total: int, event_id: str = EVENT_1, **extra: Any):  # type: ignore[no-untyped-def]
        data = {"order_reference": reference, "amount": total, "currency": "EUR"}
        body = event_body(id=event_id, data=data, **extra)
        return self.receive.execute(body, sign(body), event_id)

    def order_status(self, order_id: str) -> str:
        with Session(self.engine) as session:
            return session.scalars(select(OrderModel.status).where(OrderModel.id == order_id)).one()

    def reservations(self, order_id: str) -> list[str]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(StockReservationModel.status).where(
                        StockReservationModel.order_id == order_id
                    )
                )
            )

    def stock(self) -> int:
        with Session(self.engine) as session:
            return session.scalars(select(OrderProductModel.stock)).one()

    def attempt_status(self, order_id: str) -> str:
        with Session(self.engine) as session:
            return session.scalars(
                select(PaymentAttemptModel.status).where(PaymentAttemptModel.order_id == order_id)
            ).one()

    def stored_events(self) -> dict[str, tuple[str, str | None]]:
        with Session(self.engine) as session:
            rows = session.scalars(select(PaymentWebhookEventModel)).all()
            return {row.id: (row.outcome, row.paid_order_id) for row in rows}


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


class TestPaymentSucceededOnTheDatabase:
    def test_pays_the_order_keeps_the_stock_out_and_makes_the_reservation_definitive(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order(quantity=2)
        assert (shop.stock(), shop.reservations(order_id)) == (8, ["reserved"])

        receipt = shop.webhook(reference, total)

        assert receipt.outcome is WebhookOutcome.APPLIED
        assert shop.order_status(order_id) == "paid"
        assert shop.attempt_status(order_id) == "succeeded"
        assert (shop.stock(), shop.reservations(order_id)) == (8, ["committed"])
        assert shop.stored_events() == {EVENT_1: ("applied", order_id)}

    def test_the_mail_carries_the_number_the_lines_and_the_total_of_the_order(
        self, shop: _Shop
    ) -> None:
        _order_id, reference, total = shop.pending_order(quantity=2)

        receipt = shop.webhook(reference, total)

        assert receipt.mail is not None
        assert (receipt.mail.to, receipt.mail.total_cents) == (EMAIL, total)
        assert receipt.mail.order_number.startswith("BC-")
        assert [(m.name, m.quantity, m.line_total_cents) for m in receipt.mail.lines] == [
            ("Popote", 2, 7800)
        ]

    def test_a_replay_survives_a_new_use_case_instance_and_changes_nothing(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()
        shop.webhook(reference, total)
        restarted = _Shop(shop.engine)  # nouveau processus : aucun état en mémoire

        again = restarted.webhook(reference, total)

        assert again.outcome is WebhookOutcome.REPLAYED and again.mail is None
        assert shop.stored_events() == {EVENT_1: ("applied", order_id)}

    def test_a_second_event_for_the_same_order_is_remembered_but_confirms_nothing(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()
        shop.webhook(reference, total, EVENT_1)

        second = shop.webhook(reference, total, EVENT_2)

        assert (second.outcome, second.reason) == (
            WebhookOutcome.IGNORED,
            "order_already_confirmed",
        )
        assert shop.stored_events() == {EVENT_1: ("applied", order_id), EVENT_2: ("ignored", None)}

    def test_the_database_itself_refuses_two_events_confirming_the_same_order(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()
        shop.webhook(reference, total, EVENT_1)

        with Session(shop.engine) as session, pytest.raises(IntegrityError):
            session.add(
                PaymentWebhookEventModel(
                    id=EVENT_2,
                    event_type="payment.succeeded",
                    outcome="applied",
                    paid_order_id=order_id,
                    received_at=datetime.now(UTC),
                )
            )
            session.commit()

    def test_an_order_paid_by_the_synchronous_path_is_still_confirmed_by_the_webhook(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()
        with Session(shop.engine) as session:
            session.execute(
                update(OrderModel).where(OrderModel.id == order_id).values(status="paid")
            )
            session.commit()

        receipt = shop.webhook(reference, total)

        assert receipt.outcome is WebhookOutcome.APPLIED and receipt.mail is not None
        assert shop.reservations(order_id) == ["committed"]


class TestEventsThatMustNotPay:
    def test_a_wrong_amount_leaves_the_order_pending_and_its_stock_reserved(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()

        receipt = shop.webhook(reference, total - 1)

        assert receipt.reason == "amount_mismatch"
        assert shop.order_status(order_id) == "pending_payment"
        assert shop.reservations(order_id) == ["reserved"]

    def test_an_unknown_reference_is_acknowledged_and_remembered(self, shop: _Shop) -> None:
        receipt = shop.webhook("BC-INCONNU", 100)

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "order_not_found")
        assert shop.stored_events() == {EVENT_1: ("ignored", None)}

    def test_a_payment_arriving_after_expiration_does_not_resurrect_the_order(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order(quantity=3)
        with Session(shop.engine) as session:
            session.execute(
                update(OrderModel)
                .where(OrderModel.id == order_id)
                .values(created_at=NOW_UTC - timedelta(minutes=40))
            )
            session.commit()
        ExpireUnpaidOrdersUseCase(
            lambda: SqlAlchemyExpirationUnitOfWork(shop.engine),
            shop.events,
            clock=lambda: NOW_UTC,
            ttl_minutes=30,
        ).execute()

        receipt = shop.webhook(reference, total)

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "order_expired")
        assert shop.order_status(order_id) == "expired"
        assert (shop.stock(), shop.reservations(order_id)) == (10, ["released"])

    def test_a_declined_payment_marks_the_attempt_failed_and_leaves_the_order_payable(
        self, shop: _Shop
    ) -> None:
        order_id, reference, total = shop.pending_order()
        data = {"order_reference": reference, "amount": total, "currency": "EUR"}
        body = event_body(type="payment.failed", data=data)

        receipt = shop.receive.execute(body, sign(body), EVENT_1)

        assert receipt.outcome is WebhookOutcome.APPLIED and receipt.mail is None
        assert shop.attempt_status(order_id) == "failed"
        assert shop.order_status(order_id) == "pending_payment"
        assert shop.stored_events() == {EVENT_1: ("applied", None)}


NOW_UTC = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
