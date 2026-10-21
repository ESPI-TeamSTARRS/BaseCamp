"""POST /webhooks/payment : 401 / 400 / 200, email après la réponse, journaux conformes au schéma."""

import io
import json
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient, Response
from jsonschema import Draft202012Validator

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.order.domain.enums.order_status import OrderStatus
from app.payment_confirmation.__tests__.fakes import (
    EMAIL,
    EVENT_ID,
    NOW,
    ORDER_NUMBER,
    OTHER_EVENT_ID,
    REFERENCE,
    SECRET,
    TOTAL_CENTS,
    ConfirmationStore,
    FakeConfirmationUnitOfWork,
    RecordingSender,
    event_body,
    sign,
    store_with,
)
from app.payment_confirmation.application.receive_payment_webhook import (
    ReceivePaymentWebhookUseCase,
)
from app.payment_confirmation.application.send_order_confirmation import (
    SendOrderConfirmationUseCase,
)
from app.payment_confirmation.domain.services.webhook_signature_verifier import (
    WebhookSignatureVerifier,
)

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
PATH = "/webhooks/payment"


class _Pseudonymizer:
    def pseudonymize(self, email: str) -> str:
        return "0123456789abcdef"


class _Client:
    def __init__(
        self,
        store: ConfirmationStore | None = None,
        sender: RecordingSender | None = None,
        events: Any = None,
    ) -> None:
        self.store = store or store_with()
        self.sender = sender or RecordingSender()
        self.events = events or InMemoryBusinessEventLogger()
        self.application = create_app()
        self.application.state.receive_payment_webhook_use_case = ReceivePaymentWebhookUseCase(
            lambda: FakeConfirmationUnitOfWork(self.store),
            WebhookSignatureVerifier((SECRET,), 300, lambda: NOW),
            self.events,
        )
        self.application.state.send_order_confirmation_use_case = SendOrderConfirmationUseCase(
            self.sender, self.events, _Pseudonymizer()
        )

    async def post(
        self, body: bytes, signature: str | None = "signed", event_id: str | None = EVENT_ID
    ) -> Response:
        headers = {"X-Correlation-ID": CORRELATION_ID, "Content-Type": "application/json"}
        if signature is not None:
            headers["X-Payment-Signature"] = sign(body) if signature == "signed" else signature
        if event_id is not None:
            headers["X-Payment-Event-Id"] = event_id
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            return await client.post(PATH, content=body, headers=headers)


class TestAcceptedWebhook:
    async def test_a_signed_success_pays_the_order_and_sends_the_email_after_the_response(
        self,
    ) -> None:
        client = _Client()

        response = await client.post(event_body())

        assert (response.status_code, response.json()) == (200, {"status": "applied"})
        assert client.store.targets[REFERENCE].order_status is OrderStatus.PAID
        (mail,) = client.sender.sent
        assert (mail.to, mail.order_number, mail.total_cents) == (EMAIL, ORDER_NUMBER, TOTAL_CENTS)

    async def test_the_same_event_id_replayed_answers_200_without_a_second_email(self) -> None:
        client = _Client()
        await client.post(event_body())

        again = await client.post(event_body())

        assert (again.status_code, again.json()) == (200, {"status": "replayed"})
        assert len(client.sender.sent) == 1

    async def test_an_email_outage_never_fails_the_webhook(self) -> None:
        client = _Client(sender=RecordingSender(failing=True))

        response = await client.post(event_body())

        assert response.status_code == 200
        assert client.store.targets[REFERENCE].order_status is OrderStatus.PAID
        failed = [e for e in client.events.events if e.event == "order.confirmation_email_failed"]
        assert len(failed) == 1

    async def test_an_unrelated_event_is_acknowledged_without_effect(self) -> None:
        client = _Client()

        response = await client.post(event_body(type="refund.succeeded"))

        assert (response.status_code, response.json()) == (200, {"status": "ignored"})
        assert client.sender.sent == []


class TestRejectedWebhook:
    async def test_a_missing_or_invalid_signature_returns_401_and_changes_nothing(self) -> None:
        client = _Client()
        body = event_body()

        missing = await client.post(body, signature=None)
        wrong = await client.post(body, signature=f"t={NOW},v1={'0' * 64}")
        stale = await client.post(body, signature=sign(body, timestamp=NOW - 400))

        for response in (missing, wrong, stale):
            assert (response.status_code, response.json()) == (
                401,
                {"detail": "Signature invalide."},
            )
        assert client.store.events == {}
        assert client.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT
        assert client.sender.sent == []

    async def test_an_altered_body_returns_401(self) -> None:
        client = _Client()
        signature = sign(event_body())
        altered = event_body(
            data={"order_reference": REFERENCE, "amount": 1, "currency": "EUR", "status": "x"}
        )

        response = await client.post(altered, signature=signature)

        assert response.status_code == 401
        assert client.store.targets[REFERENCE].order_status is OrderStatus.PENDING_PAYMENT

    async def test_a_signed_but_malformed_body_returns_400_without_echo(self) -> None:
        client = _Client()

        response = await client.post(b'{"id": 12, "secret": "x"}')

        assert (response.status_code, response.json()) == (400, {"detail": "Evenement invalide."})

    async def test_a_header_id_that_differs_from_the_body_returns_400(self) -> None:
        client = _Client()

        response = await client.post(event_body(), event_id=OTHER_EVENT_ID)

        assert response.status_code == 400
        assert client.store.events == {}


class TestLogsFollowTheSchema:
    async def test_every_line_validates_and_nothing_sensitive_is_written(self) -> None:
        stream = io.StringIO()
        client = _Client(events=StructlogBusinessEventLogger("basecamp-shop", stream))
        body = event_body()
        await client.post(body)
        await client.post(body)
        await client.post(body, signature=f"t={NOW},v1={'0' * 64}")
        await client.post(b"pas du json")
        await client.post(event_body(id=OTHER_EVENT_ID), event_id=OTHER_EVENT_ID)

        output = stream.getvalue()
        lines = [json.loads(line) for line in output.splitlines() if line.strip()]
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        for line in lines:
            validator.validate(line)
        names = [line["event"] for line in lines]
        assert names == [
            "payment.webhook_received",
            "order.paid",
            "order.confirmation_email_sent",
            "payment.webhook_replayed",
            "payment.webhook_rejected",
            "payment.webhook_rejected",
            "payment.webhook_received",
            "payment.webhook_ignored",
        ]
        assert SECRET not in output and EMAIL not in output
        assert all(line["correlation_id"] == CORRELATION_ID for line in lines[:2])
