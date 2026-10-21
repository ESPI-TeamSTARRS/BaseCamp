"""Réception du webhook de paiement : signature, rejeu, effets sur la commande, le stock et les logs."""

import json

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.order.domain.enums.order_status import OrderStatus
from app.payment_confirmation.__tests__.fakes import (
    ATTEMPT_ID,
    EMAIL,
    EVENT_ID,
    NOW,
    ORDER_ID,
    ORDER_NUMBER,
    OTHER_EVENT_ID,
    REFERENCE,
    SECRET,
    TOTAL_CENTS,
    ConfirmationStore,
    FakeConfirmationUnitOfWork,
    event_body,
    sign,
    store_with,
    target,
)
from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.domain.enums.webhook_outcome import WebhookOutcome
from app.payment_confirmation.domain.errors.invalid_webhook_payload_error import (
    InvalidWebhookPayloadError,
)
from app.payment_confirmation.domain.errors.invalid_webhook_signature_error import (
    InvalidWebhookSignatureError,
)
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)


class _Setup:
    def __init__(
        self, store: ConfirmationStore | None = None, duplicate_on_commit: bool = False
    ) -> None:
        self.store = store or store_with()
        self.events = InMemoryBusinessEventLogger()
        self.units: list[FakeConfirmationUnitOfWork] = []

        def factory() -> FakeConfirmationUnitOfWork:
            unit = FakeConfirmationUnitOfWork(self.store, duplicate_on_commit)
            self.units.append(unit)
            return unit

        self.use_case = ReceivePaymentWebhookUseCase(
            factory,
            WebhookSignatureVerifier((SECRET,), 300, lambda: NOW),
            self.events,
        )

    def receive(self, body: bytes, header: str | None = "signed", event_id: str | None = EVENT_ID):  # type: ignore[no-untyped-def]
        signature = sign(body) if header == "signed" else header
        return self.use_case.execute(body, signature, event_id)

    def names(self) -> list[str]:
        return [event.event for event in self.events.events]


class TestPaymentSucceeded:
    def test_marks_the_order_paid_commits_the_stock_and_returns_the_mail(self) -> None:
        setup = _Setup()

        receipt = setup.receive(event_body())

        assert receipt.outcome is WebhookOutcome.APPLIED
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PAID
        assert setup.store.committed_orders == [ORDER_ID]
        assert setup.store.attempt_statuses == {ATTEMPT_ID: "succeeded"}
        assert setup.store.events[EVENT_ID][:2] == ("payment.succeeded", WebhookOutcome.APPLIED)
        assert setup.store.confirmed_orders == {ORDER_ID}
        assert receipt.mail is not None
        assert (receipt.mail.to, receipt.mail.order_number, receipt.mail.total_cents) == (
            EMAIL,
            ORDER_NUMBER,
            TOTAL_CENTS,
        )

    def test_emits_the_received_and_paid_events_without_secret_or_email(self) -> None:
        setup = _Setup()

        setup.receive(event_body())

        assert setup.names() == ["payment.webhook_received", "order.paid"]
        paid = setup.events.events[1]
        assert (paid.resource_type, paid.resource_id) == ("order", ORDER_NUMBER)
        assert paid.attributes["amount_cents"] == TOTAL_CENTS
        serialized = json.dumps([vars(event) for event in setup.events.events], default=str)
        assert SECRET not in serialized and EMAIL not in serialized

    def test_an_order_already_paid_by_the_synchronous_path_is_still_confirmed_once(self) -> None:
        setup = _Setup(store_with(OrderStatus.PAID))

        receipt = setup.receive(event_body())

        assert receipt.outcome is WebhookOutcome.APPLIED
        assert setup.units[0].targets.paid == []
        assert setup.store.committed_orders == [ORDER_ID]
        assert receipt.mail is not None

    def test_without_the_event_id_header_the_body_id_is_used(self) -> None:
        setup = _Setup()

        receipt = setup.receive(event_body(), event_id=None)

        assert receipt.outcome is WebhookOutcome.APPLIED


class TestReplay:
    def test_the_same_event_id_has_no_second_effect(self) -> None:
        setup = _Setup()
        setup.receive(event_body())
        committed_before = list(setup.store.committed_orders)

        again = setup.receive(event_body())

        assert again.outcome is WebhookOutcome.REPLAYED
        assert again.mail is None
        assert setup.store.committed_orders == committed_before
        assert setup.units[1].events.recorded == []
        assert setup.names()[-1] == "payment.webhook_replayed"

    def test_a_concurrent_duplicate_lost_at_commit_is_a_replay(self) -> None:
        setup = _Setup(duplicate_on_commit=True)

        receipt = setup.receive(event_body())

        assert receipt.outcome is WebhookOutcome.REPLAYED
        assert receipt.mail is None
        assert setup.names()[-1] == "payment.webhook_replayed"

    def test_another_event_for_an_already_confirmed_order_changes_nothing(self) -> None:
        setup = _Setup()
        setup.receive(event_body())

        receipt = setup.receive(event_body(id=OTHER_EVENT_ID), event_id=OTHER_EVENT_ID)

        assert receipt.outcome is WebhookOutcome.IGNORED
        assert receipt.reason == "order_already_confirmed"
        assert receipt.mail is None
        assert setup.store.committed_orders == [ORDER_ID]
        assert setup.store.events[OTHER_EVENT_ID][1] is WebhookOutcome.IGNORED


class TestRejected:
    @pytest.mark.parametrize(
        ("header", "reason"),
        [
            (None, "signature_missing"),
            ("t=abc", "signature_malformed"),
            (f"t={NOW},v1={'0' * 64}", "signature_mismatch"),
            (f"t={NOW - 301},v1={'0' * 64}", "timestamp_out_of_window"),
        ],
    )
    def test_a_bad_signature_changes_nothing_and_is_logged_with_its_reason(
        self, header: str | None, reason: str
    ) -> None:
        setup = _Setup()

        with pytest.raises(InvalidWebhookSignatureError):
            setup.use_case.execute(event_body(), header, EVENT_ID)

        assert setup.units == []
        assert setup.store.events == {}
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT
        rejected = setup.events.events[-1]
        assert (rejected.event, rejected.reason) == ("payment.webhook_rejected", reason)

    def test_an_altered_body_is_rejected_before_any_state_is_read(self) -> None:
        setup = _Setup()
        signature = sign(event_body())
        altered = event_body(data={"order_reference": REFERENCE, "amount": 1, "currency": "EUR"})

        with pytest.raises(InvalidWebhookSignatureError):
            setup.use_case.execute(altered, signature, EVENT_ID)

        assert setup.units == []

    def test_a_signed_but_malformed_body_is_a_payload_error(self) -> None:
        setup = _Setup()

        with pytest.raises(InvalidWebhookPayloadError):
            setup.receive(b"pas du json")

        assert setup.names() == ["payment.webhook_rejected"]
        assert setup.units == []

    def test_a_header_event_id_that_differs_from_the_body_is_refused(self) -> None:
        setup = _Setup()

        with pytest.raises(InvalidWebhookPayloadError):
            setup.receive(event_body(), event_id=OTHER_EVENT_ID)

        assert setup.store.events == {}


class TestAcknowledgedWithoutEffect:
    def test_an_unknown_reference_is_acknowledged_and_remembered(self) -> None:
        setup = _Setup(ConfirmationStore())

        receipt = setup.receive(event_body())

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "order_not_found")
        assert setup.store.events[EVENT_ID][1] is WebhookOutcome.IGNORED
        assert setup.names() == ["payment.webhook_received", "payment.webhook_ignored"]

    def test_an_amount_that_differs_from_the_order_never_pays_it(self) -> None:
        setup = _Setup()
        data = {"order_reference": REFERENCE, "amount": TOTAL_CENTS - 1, "currency": "EUR"}

        receipt = setup.receive(event_body(data=data))

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "amount_mismatch")
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT
        assert setup.store.committed_orders == []

    def test_a_currency_that_is_not_eur_never_pays_the_order(self) -> None:
        setup = _Setup()
        data = {"order_reference": REFERENCE, "amount": TOTAL_CENTS, "currency": "USD"}

        receipt = setup.receive(event_body(data=data))

        assert receipt.reason == "currency_mismatch"
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT

    def test_an_expired_order_is_not_paid_and_its_stock_stays_released(self) -> None:
        setup = _Setup(store_with(OrderStatus.EXPIRED))

        receipt = setup.receive(event_body())

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.REJECTED, "order_expired")
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.EXPIRED
        assert setup.store.committed_orders == []
        assert receipt.mail is None
        stored = setup.store.events[EVENT_ID]
        assert (stored[1], stored[2]) == (WebhookOutcome.IGNORED, "order_expired")

    def test_the_same_late_payment_replayed_is_rejected_again_never_acknowledged(self) -> None:
        setup = _Setup(store_with(OrderStatus.EXPIRED))
        setup.receive(event_body())

        again = setup.receive(event_body())

        assert (again.outcome, again.reason) == (WebhookOutcome.REJECTED, "order_expired")
        assert setup.units[1].events.recorded == []

    def test_a_late_failure_on_an_expired_order_is_not_a_rejection(self) -> None:
        setup = _Setup(store_with(OrderStatus.EXPIRED))

        receipt = setup.receive(event_body(type="payment.failed"))

        assert receipt.outcome is not WebhookOutcome.REJECTED

    def test_other_ignored_payments_stay_acknowledged_with_200(self) -> None:
        setup = _Setup()

        receipt = setup.receive(
            event_body(
                data={
                    "order_reference": REFERENCE,
                    "amount": 1,
                    "currency": "EUR",
                    "status": "succeeded",
                }
            )
        )

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "amount_mismatch")

    def test_an_unsupported_event_type_is_acknowledged_without_effect(self) -> None:
        setup = _Setup()
        body = event_body(type="payment.pending")

        receipt = setup.receive(body)

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "unsupported_type")
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT


class TestPaymentFailed:
    def test_marks_the_attempt_failed_and_keeps_the_order_payable(self) -> None:
        setup = _Setup()
        body = event_body(
            type="payment.failed",
            data={
                "order_reference": REFERENCE,
                "amount": TOTAL_CENTS,
                "currency": "EUR",
                "status": "failed",
            },
        )

        receipt = setup.receive(body)

        assert receipt.outcome is WebhookOutcome.APPLIED
        assert receipt.mail is None
        assert setup.store.attempt_statuses == {ATTEMPT_ID: "failed"}
        assert setup.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT
        assert setup.store.committed_orders == []
        assert setup.store.confirmed_orders == set()

    def test_a_late_failure_never_downgrades_a_succeeded_attempt(self) -> None:
        store = ConfirmationStore(
            targets={REFERENCE: target(OrderStatus.PAID, attempt_status="succeeded")}
        )
        setup = _Setup(store)
        body = event_body(type="payment.failed")

        receipt = setup.receive(body)

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "attempt_settled")
        assert setup.store.attempt_statuses == {}


def _refund_body(refunded: int | None, amount: int = 1000) -> bytes:
    data: dict[str, object] = {
        "refund_id": "r-1",
        "payment_intent_id": "7d2f3c1e-8a41-4d3b-9c55-2a6e0f9b1c42",
        "order_reference": REFERENCE,
        "amount": amount,
        "currency": "EUR",
        "status": "succeeded",
    }
    if refunded is not None:
        data["amount_refunded"] = refunded
    return event_body(type="refund.succeeded", data=data)


def _paid_store(refunded_cents: int = 0) -> ConfirmationStore:
    return ConfirmationStore(
        targets={
            REFERENCE: target(
                OrderStatus.PAID, attempt_status="succeeded", refunded_cents=refunded_cents
            )
        }
    )


class TestRefundSucceeded:
    def test_a_partial_refund_is_recorded_and_the_order_stays_paid(self) -> None:
        setup = _Setup(_paid_store())

        receipt = setup.receive(_refund_body(1000))

        assert (receipt.outcome, receipt.reason, receipt.mail) == (
            WebhookOutcome.APPLIED,
            None,
            None,
        )
        current = setup.store.targets[REFERENCE]
        assert (current.order_status, current.refunded_cents) == (OrderStatus.PAID, 1000)
        refunded = [e for e in setup.events.events if e.event == "order.refunded"]
        assert len(refunded) == 1
        assert refunded[0].resource_id == ORDER_NUMBER
        assert refunded[0].attributes["amount_refunded_cents"] == 1000

    def test_a_full_refund_marks_the_order_refunded(self) -> None:
        setup = _Setup(_paid_store())

        setup.receive(_refund_body(TOTAL_CENTS, amount=TOTAL_CENTS))

        current = setup.store.targets[REFERENCE]
        assert (current.order_status, current.refunded_cents) == (
            OrderStatus.REFUNDED,
            TOTAL_CENTS,
        )

    def test_a_later_refund_completes_a_partial_one(self) -> None:
        setup = _Setup(_paid_store(refunded_cents=1000))

        setup.receive(_refund_body(TOTAL_CENTS, amount=3490), event_id=None)

        assert setup.store.targets[REFERENCE].order_status is OrderStatus.REFUNDED

    @pytest.mark.parametrize(
        ("refunded", "reason"),
        [
            (3000, "refund_already_recorded"),
            (1000, "refund_already_recorded"),
            (TOTAL_CENTS + 1, "refund_exceeds_total"),
            (None, "refund_amount_missing"),
        ],
    )
    def test_a_replayed_older_excessive_or_incomplete_refund_changes_nothing(
        self, refunded: int | None, reason: str
    ) -> None:
        setup = _Setup(_paid_store(refunded_cents=3000))

        receipt = setup.receive(_refund_body(refunded), event_id=None)

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, reason)
        assert setup.store.targets[REFERENCE].refunded_cents == 3000

    def test_the_same_event_id_is_never_applied_twice(self) -> None:
        setup = _Setup(_paid_store())
        body = _refund_body(1000)
        setup.receive(body)
        setup.events.events.clear()

        receipt = setup.receive(body)

        assert receipt.outcome is WebhookOutcome.REPLAYED
        assert [e for e in setup.events.events if e.event == "order.refunded"] == []

    def test_a_refund_on_an_unpaid_order_is_ignored(self) -> None:
        setup = _Setup()

        receipt = setup.receive(_refund_body(1000))

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "order_not_paid")
        assert setup.store.targets[REFERENCE].refunded_cents == 0

    def test_a_refund_for_an_unknown_reference_is_acknowledged(self) -> None:
        setup = _Setup(ConfirmationStore())

        receipt = setup.receive(_refund_body(1000))

        assert (receipt.outcome, receipt.reason) == (WebhookOutcome.IGNORED, "order_not_found")
