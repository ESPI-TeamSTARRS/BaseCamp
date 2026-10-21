"""Du POST /confirm à la livraison signée : outbox, worker, journaux conformes au schéma commun."""

import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event, text

from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase
from app.webhook.domain.services.webhook_signer import WebhookSigner
from app.webhook.domain.value_objects.delivery_result import DeliveryResult
from app.webhook.domain.interfaces.webhook_sender import WebhookSender
from app.webhook.infrastructure.repositories.sqlalchemy_delivery_unit_of_work import (
    SqlAlchemyDeliveryUnitOfWork,
)
from app.webhook.application.deliver_next_event import DeliverNextEventUseCase
from app.webhook.application.requeue_dead_events import RequeueDeadEventsUseCase
from app.webhook.domain.value_objects.retry_policy import RetryPolicy

TOKEN = "tok-shop-test-0001"
SECRET = "whsec_flow_0123456789abcdef0123456789abcdef"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
POLICY = RetryPolicy(max_attempts=2, base_seconds=5, max_delay_seconds=60)


class RecordingSender(WebhookSender):
    def __init__(self) -> None:
        self.answers: list[DeliveryResult] = []
        self.sent: list[tuple[UUID, str, str]] = []

    def send(self, event_id: UUID, body: str, signature: str) -> DeliveryResult:
        self.sent.append((event_id, body, signature))
        return self.answers.pop(0) if self.answers else DeliveryResult.ok(200)


@dataclass
class Env:
    client: TestClient
    engine: Engine
    log: io.StringIO
    sender: RecordingSender
    clock: list[datetime]

    def deliver(self) -> bool:
        use_case = DeliverNextEventUseCase(
            SqlAlchemyDeliveryUnitOfWork(self.engine),
            self.sender,
            WebhookSigner([SECRET]),
            POLICY,
            lambda: self.clock[0],
            StructlogBusinessEventLogger("basecamp-payment", self.log),
        )
        return use_case.execute()

    def logged(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.getvalue().splitlines() if line]


@pytest.fixture
def env() -> Iterator[Env]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings(service_tokens={"shop": TOKEN}, provider_timeout_seconds=0.1)
    log = io.StringIO()
    application = create_app(
        settings, engine, StructlogBusinessEventLogger(settings.service_name, log)
    )
    now = datetime.now(UTC) + timedelta(hours=1)  # les événements écrits par le test sont échus
    with TestClient(application) as client:
        yield Env(client, engine, log, RecordingSender(), [now])


def _confirm(env: Env, method: str = "pm_test_success", order: str = "CMD-1") -> str:
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": f"create-{order}-key"}
    created = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 4990, "currency": "EUR"},
        headers=headers,
    )
    intent_id = str(created.json()["id"])
    headers["Idempotency-Key"] = f"confirm-{order}-key"
    response = env.client.post(
        f"/payments/intents/{intent_id}/confirm", json={"payment_method": method}, headers=headers
    )
    assert response.status_code == 200
    return intent_id


def _outbox(env: Env) -> list[tuple[str, str, int]]:
    with env.engine.connect() as connection:
        rows = connection.execute(text("SELECT event_type, status, attempts FROM outbox"))
        return [(row[0], row[1], row[2]) for row in rows]


class TestConfirmationWritesTheEvent:
    def test_a_confirmed_payment_leaves_one_pending_payment_succeeded_event(self, env: Env) -> None:
        _confirm(env)

        assert _outbox(env) == [("payment.succeeded", "pending", 0)]

    def test_a_declined_payment_leaves_a_payment_failed_event(self, env: Env) -> None:
        _confirm(env, "pm_test_declined")

        assert _outbox(env) == [("payment.failed", "pending", 0)]

    def test_replaying_the_confirmation_does_not_add_an_event(self, env: Env) -> None:
        intent_id = _confirm(env)
        headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "confirm-CMD-1-key"}

        env.client.post(
            f"/payments/intents/{intent_id}/confirm",
            json={"payment_method": "pm_test_success"},
            headers=headers,
        )

        assert len(_outbox(env)) == 1


class TestDelivery:
    def test_the_worker_posts_the_signed_event_and_marks_it_delivered(self, env: Env) -> None:
        intent_id = _confirm(env)

        assert env.deliver() is True

        ((event_id, body, signature),) = env.sender.sent
        payload = json.loads(body)
        assert payload["id"] == str(event_id)
        assert payload["type"] == "payment.succeeded"
        assert payload["data"]["payment_intent_id"] == intent_id
        assert WebhookSigner([SECRET]).verify(signature, body, now=int(env.clock[0].timestamp()))
        assert _outbox(env) == [("payment.succeeded", "delivered", 1)]
        assert env.deliver() is False

    def test_a_shop_outage_never_blocks_a_confirmation_and_delivery_resumes_later(
        self, env: Env
    ) -> None:
        env.sender.answers = [DeliveryResult.failed("connection_error")]
        _confirm(env, order="CMD-1")
        env.deliver()
        _confirm(env, order="CMD-2")  # la boutique est toujours en panne : la confirmation passe

        assert env.deliver() is True  # CMD-2 est échu, CMD-1 attend sa relance
        env.clock[0] += timedelta(seconds=10)
        assert env.deliver() is True

        statuses = sorted(status for _, status, _ in _outbox(env))
        assert statuses == ["delivered", "delivered"]
        first_id = env.sender.sent[0][0]
        assert [sent[0] for sent in env.sender.sent].count(first_id) == 2

    def test_a_dead_event_can_be_requeued_and_arrives_again_with_the_same_id(
        self, env: Env
    ) -> None:
        env.sender.answers = [DeliveryResult.failed("http_500", 500)] * 2
        _confirm(env)
        env.deliver()
        env.clock[0] += timedelta(minutes=1)
        env.deliver()
        assert _outbox(env) == [("payment.succeeded", "dead", 2)]

        requeued = RequeueDeadEventsUseCase(
            SqlAlchemyDeliveryUnitOfWork(env.engine),
            lambda: env.clock[0],
            StructlogBusinessEventLogger("basecamp-payment", env.log),
        ).execute(None)
        env.deliver()

        assert requeued == 1
        assert _outbox(env) == [("payment.succeeded", "delivered", 1)]
        assert len({sent[0] for sent in env.sender.sent}) == 1


class TestJournal:
    def test_every_line_respects_the_common_schema_and_no_secret_is_logged(self, env: Env) -> None:
        env.sender.answers = [DeliveryResult.failed("http_503", 503)] * 2
        _confirm(env)
        env.deliver()
        env.clock[0] += timedelta(minutes=1)
        env.deliver()
        RequeueDeadEventsUseCase(
            SqlAlchemyDeliveryUnitOfWork(env.engine),
            lambda: env.clock[0],
            StructlogBusinessEventLogger("basecamp-payment", env.log),
        ).execute(None)
        env.deliver()

        lines = env.logged()
        for line in lines:
            assert not list(VALIDATOR.iter_errors(line)), line
        names = [line["event"] for line in lines]
        assert names.count("webhook.event_queued") == 1
        assert names.count("webhook.delivery_failed") == 1
        assert names.count("webhook.event_dead") == 1
        assert names.count("webhook.event_requeued") == 1
        assert names.count("webhook.delivered") == 1
        dead = next(line for line in lines if line["event"] == "webhook.event_dead")
        assert (dead["level"], dead["outcome"], dead["reason"]) == (
            "error",
            "error",
            "max_attempts_reached",
        )
        raw = env.log.getvalue()
        assert SECRET not in raw
        assert "v1=" not in raw
        assert "order_reference" not in raw.split("webhook.event_queued")[1].split("\n")[0]
