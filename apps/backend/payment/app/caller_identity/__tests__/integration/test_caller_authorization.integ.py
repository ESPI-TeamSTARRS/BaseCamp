import io
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import StaticPool, create_engine

from app.caller_identity.__tests__.tokens import (
    JWKS,
    KEY,
    REFUND_TOKEN,
    SHOP_TOKEN,
    SigningKey,
    StaticJwks,
)
from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

OPERATOR = KEY.token(sub="operator-7", use="client", roles=["operator"])
CUSTOMER = KEY.token(sub="customer-3", use="client", roles=["customer"])
UNKNOWN_INTENT = "00000000-0000-0000-0000-000000000000"


@dataclass
class Env:
    client: TestClient
    log: io.StringIO
    jwks: StaticJwks


@pytest.fixture
def env() -> Iterator[Env]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings(provider_timeout_seconds=0.1)
    log = io.StringIO()
    events = StructlogBusinessEventLogger(settings.service_name, log)
    jwks = StaticJwks(KEY)
    with TestClient(create_app(settings, engine, events, jwks_source=jwks)) as client:
        yield Env(client, log, jwks)


def _create(env: Env, token: str | None, order: str = "CMD-1") -> Response:
    headers = {"Idempotency-Key": f"create-{order}-key"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response: Response = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": 10000, "currency": "EUR"},
        headers=headers,
    )
    return response


def _refund(env: Env, token: str, intent_id: str = UNKNOWN_INTENT) -> Response:
    response: Response = env.client.post(
        f"/payments/intents/{intent_id}/refunds",
        json={"amount": 1000},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "refund-0001"},
    )
    return response


def _paid_intent(env: Env) -> str:
    created = _create(env, SHOP_TOKEN)
    intent_id = str(created.json()["id"])
    env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": "pm_test_success"},
        headers={"Authorization": f"Bearer {SHOP_TOKEN}", "Idempotency-Key": "confirm-1-key"},
    )
    return intent_id


def _events(env: Env) -> list[dict[str, object]]:
    return [json.loads(line) for line in env.log.getvalue().splitlines() if line.startswith("{")]


class TestTokensRefused:
    def test_no_token(self, env: Env) -> None:
        assert _create(env, None).status_code == 401

    def test_an_expired_token(self, env: Env) -> None:
        token = KEY.token(issued_at=time.time() - 3600, lifetime=60)

        assert _create(env, token).status_code == 401

    def test_a_forged_token(self, env: Env) -> None:
        assert _create(env, SigningKey(KEY.kid).token()).status_code == 401

    def test_a_token_for_another_audience(self, env: Env) -> None:
        assert _create(env, KEY.token(audience="shop")).status_code == 401

    def test_a_client_token_replayed_on_a_service_route(self, env: Env) -> None:
        assert _create(env, OPERATOR).status_code == 401

    def test_every_refusal_has_the_same_body(self, env: Env) -> None:
        bodies = {
            _create(env, token).text
            for token in (None, SigningKey(KEY.kid).token(), KEY.token(audience="shop"), OPERATOR)
        }

        assert len(bodies) == 1

    def test_the_token_itself_is_never_logged(self, env: Env) -> None:
        _create(env, KEY.token(audience="shop"))

        assert "eyJ" not in env.log.getvalue()


class TestScopes:
    def test_a_service_token_without_the_scope_is_forbidden(self, env: Env) -> None:
        assert _create(env, KEY.token(scope="refunds:write")).status_code == 403

    def test_a_service_token_without_scope_claim_is_forbidden(self, env: Env) -> None:
        assert _create(env, KEY.token(scope=None)).status_code == 403

    def test_payments_write_is_enough_to_create_an_intent(self, env: Env) -> None:
        assert _create(env, SHOP_TOKEN).status_code == 201

    def test_payments_write_alone_cannot_refund(self, env: Env) -> None:
        assert _refund(env, SHOP_TOKEN).status_code == 403

    def test_a_forbidden_call_is_logged_with_its_caller(self, env: Env) -> None:
        _refund(env, SHOP_TOKEN)

        forbidden = [e for e in _events(env) if e["event"] == "payment.caller_forbidden"]
        assert forbidden
        assert forbidden[0]["actor_id"] == "shop"


class TestRefundCallers:
    def test_a_service_with_refunds_write_can_refund(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, REFUND_TOKEN, intent_id)

        assert response.status_code == 201

    def test_an_operator_can_refund_and_is_the_recorded_actor(self, env: Env) -> None:
        intent_id = _paid_intent(env)

        response = _refund(env, OPERATOR, intent_id)

        assert response.status_code == 201
        refunds = [e for e in _events(env) if e["event"] == "refund.succeeded"]
        assert (refunds[0]["actor_type"], refunds[0]["actor_id"]) == ("user", "operator-7")

    def test_a_customer_cannot_refund(self, env: Env) -> None:
        assert _refund(env, CUSTOMER).status_code == 403

    def test_an_operator_cannot_create_an_intent(self, env: Env) -> None:
        assert _create(env, OPERATOR).status_code == 401


class TestIdentityOutage:
    def test_no_key_ever_read_is_a_503(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(engine)
        RateLimitBase.metadata.create_all(engine)
        down = StaticJwks(KEY)
        down.down = True
        with TestClient(create_app(Settings(), engine, jwks_source=down)) as client:
            response = client.post(
                "/payments/intents",
                json={"order_reference": "CMD-1", "amount": 10000, "currency": "EUR"},
                headers={"Authorization": f"Bearer {SHOP_TOKEN}", "Idempotency-Key": "k-0000001"},
            )

        assert response.status_code == 503
        assert response.headers["Retry-After"]

    def test_keys_already_read_survive_an_outage(self, env: Env) -> None:
        assert _create(env, SHOP_TOKEN).status_code == 201

        env.jwks.down = True

        assert _create(env, SHOP_TOKEN, order="CMD-2").status_code == 201


def test_the_default_jwks_fixture_is_the_test_key() -> None:
    assert JWKS.keys[KEY.kid] == KEY.jwk
