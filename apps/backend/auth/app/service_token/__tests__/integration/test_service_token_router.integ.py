import io
import json
import re
import time
from collections.abc import Iterator

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.main import create_app
from app.service_token.application.issue_service_token import IssueServiceTokenUseCase
from app.service_token.application.service_token_services import ServiceTokenServices
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_signer import JwtTokenSigner
from app.service_token.infrastructure.clients.system_clock import SystemClock
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.models.base import Base
from app.service_token.infrastructure.models.rate_limit_counter_model import (  # noqa: F401
    RateLimitCounterModel,
)
from app.service_token.infrastructure.repositories.sqlalchemy_rate_limiter import (
    SqlAlchemyRateLimiter,
)
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)

SHOP_SECRET = "shop-secret-" + "s" * 24
SHOP_PREVIOUS_SECRET = "shop-previous-" + "p" * 24
BILLING_SECRET = "billing-secret-" + "b" * 24
WRONG_SECRET = "wrong-secret-" + "w" * 24
LIMIT = 3
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "grant_type": "client_credentials",
        "client_id": "shop",
        "client_secret": SHOP_SECRET,
        "audience": "payment",
        "scope": "payments:write",
    }
    body.update(overrides)
    return body


@pytest.fixture
def keys(signing_keys: tuple[str, str]) -> Ed25519KeyStore:
    return Ed25519KeyStore(*signing_keys)


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def client(keys: Ed25519KeyStore, events: InMemoryBusinessEventLogger) -> Iterator[TestClient]:
    with _client(keys, events) as test_client:
        yield test_client


def _client(keys: Ed25519KeyStore, events: BusinessEventLogger) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    hasher = Argon2SecretHasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))
    repository = SqlAlchemyServiceClientRepository(engine)
    scopes = frozenset({ServiceScope.PAYMENTS_WRITE})
    repository.save(
        ServiceClient("shop", scopes, hasher.hash(SHOP_SECRET), hasher.hash(SHOP_PREVIOUS_SECRET))
    )
    repository.save(ServiceClient("billing", scopes, hasher.hash(BILLING_SECRET)))
    application = create_app()
    application.state.service_token_services = ServiceTokenServices(
        issue=IssueServiceTokenUseCase(
            repository,
            hasher,
            SqlAlchemyRateLimiter(engine, LIMIT),
            JwtTokenSigner(keys),
            SystemClock(),
            Settings().jwt_issuer,
            events,
        ),
    )
    application.state.events = events
    return TestClient(application)


class TestIssueToken:
    def test_issues_a_verifiable_five_minute_eddsa_token(
        self, client: TestClient, keys: Ed25519KeyStore
    ) -> None:
        response = client.post("/internal/token", json=_body())

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 300
        assert body["scope"] == "payments:write"
        claims = jwt.decode(
            body["access_token"],
            keys.public_key_pem,
            algorithms=["EdDSA"],
            audience="payment",
            issuer="basecamp-auth",
        )
        assert claims["sub"] == "shop"
        assert claims["scope"] == "payments:write"
        assert claims["token_use"] == "service"
        assert claims["exp"] - claims["iat"] == 300
        assert abs(claims["iat"] - time.time()) < 5
        assert claims["jti"]
        assert jwt.get_unverified_header(body["access_token"])["kid"] == keys.key_id

    def test_the_response_must_never_be_cached(self, client: TestClient) -> None:
        response = client.post("/internal/token", json=_body())

        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"

    def test_the_previous_secret_still_works_during_rotation(self, client: TestClient) -> None:
        response = client.post("/internal/token", json=_body(client_secret=SHOP_PREVIOUS_SECRET))

        assert response.status_code == 200


class TestRefusals:
    def test_unknown_client_and_bad_secret_get_the_very_same_response(
        self, client: TestClient
    ) -> None:
        unknown = client.post("/internal/token", json=_body(client_id="ghost"))
        bad_secret = client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))

        assert unknown.status_code == bad_secret.status_code == 401
        assert unknown.content == bad_secret.content
        assert unknown.headers.keys() == bad_secret.headers.keys()
        assert unknown.json() == {"error": "invalid_client"}

    @pytest.mark.parametrize(
        "overrides",
        [
            {"scope": "payments:read"},
            {"scope": "payments:write unknown:scope"},
            {"audience": "shop"},
            {"audience": "unknown"},
            {"scope": ""},
        ],
    )
    def test_scope_or_audience_refusals_are_the_same_generic_401(
        self, client: TestClient, overrides: dict[str, object]
    ) -> None:
        response = client.post("/internal/token", json=_body(**overrides))

        assert response.status_code == 401
        assert response.json() == {"error": "invalid_client"}

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"grant_type": "password"},
            {"extra": "field"},
            {"client_id": "bad id!"},
            {"client_secret": ""},
            {"client_secret": "x" * 257},
            {"audience": None},
        ],
    )
    def test_malformed_requests_are_422_and_never_echo_the_secret(
        self, client: TestClient, body: dict[str, object]
    ) -> None:
        payload = _body(**body) if body else {}

        response = client.post("/internal/token", json=payload)

        assert response.status_code == 422
        assert response.json()["detail"] == "Requete invalide."
        assert SHOP_SECRET not in response.text

    def test_a_non_json_body_is_422(self, client: TestClient) -> None:
        response = client.post("/internal/token", content=b"not json", headers={"x": "y"})

        assert response.status_code == 422


class TestRateLimit:
    def test_exceeding_the_limit_gives_429_with_retry_after(self, client: TestClient) -> None:
        for _ in range(LIMIT):
            assert client.post("/internal/token", json=_body()).status_code == 200

        response = client.post("/internal/token", json=_body())

        assert response.status_code == 429
        assert response.json() == {"error": "rate_limited"}
        assert 1 <= int(response.headers["retry-after"]) <= 60

    def test_another_client_is_not_affected(self, client: TestClient) -> None:
        for _ in range(LIMIT + 1):
            client.post("/internal/token", json=_body())

        response = client.post(
            "/internal/token", json=_body(client_id="billing", client_secret=BILLING_SECRET)
        )

        assert response.status_code == 200

    def test_failed_attempts_count_too(self, client: TestClient) -> None:
        for _ in range(LIMIT):
            client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))

        response = client.post("/internal/token", json=_body())

        assert response.status_code == 429


class TestBusinessEvents:
    def test_denials_have_distinct_internal_reasons_behind_identical_responses(
        self, client: TestClient, events: InMemoryBusinessEventLogger
    ) -> None:
        unknown = client.post("/internal/token", json=_body(client_id="ghost"))
        bad_secret = client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))

        assert unknown.content == bad_secret.content
        assert [event.reason for event in events.events] == ["unknown_client", "invalid_secret"]

    def test_rate_limiting_emits_the_rate_limited_event(
        self, client: TestClient, events: InMemoryBusinessEventLogger
    ) -> None:
        for _ in range(LIMIT + 1):
            client.post("/internal/token", json=_body())

        last = events.events[-1]
        assert last.event == "auth.service_rate_limited"
        assert last.resource_id == "shop"

    def test_no_secret_token_or_email_is_ever_in_an_event(
        self, client: TestClient, events: InMemoryBusinessEventLogger
    ) -> None:
        ok = client.post("/internal/token", json=_body())
        client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))
        client.post("/internal/token", json=_body(client_id="ghost"))

        dump = repr(events.events)
        for forbidden in (SHOP_SECRET, WRONG_SECRET, ok.json()["access_token"], "@"):
            assert forbidden not in dump


class TestJsonLogLines:
    """Lignes reellement ecrites par l'adaptateur de production (contrat log-event.schema.json)."""

    @staticmethod
    def _lines(keys: Ed25519KeyStore) -> tuple[TestClient, io.StringIO]:
        stream = io.StringIO()
        return _client(keys, StructlogBusinessEventLogger("basecamp-auth", stream)), stream

    def test_issuance_and_denial_lines_follow_the_common_schema(
        self, keys: Ed25519KeyStore
    ) -> None:
        client, stream = self._lines(keys)

        client.post("/internal/token", json=_body(), headers={"X-Correlation-ID": CORRELATION_ID})
        client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))

        issued, denied = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert issued["service"] == "basecamp-auth"
        assert (issued["level"], issued["event"], issued["outcome"]) == (
            "info",
            "auth.service_token_issued",
            "success",
        )
        assert issued["correlation_id"] == CORRELATION_ID
        assert (issued["resource_type"], issued["resource_id"]) == ("service_client", "shop")
        assert "reason" not in issued
        assert (denied["level"], denied["event"], denied["reason"]) == (
            "warning",
            "auth.service_token_denied",
            "invalid_secret",
        )
        assert re.fullmatch(r"[A-Za-z0-9-]{8,64}", denied["correlation_id"])
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", issued["timestamp"])

    def test_the_lines_never_contain_a_secret_or_a_token(self, keys: Ed25519KeyStore) -> None:
        client, stream = self._lines(keys)

        ok = client.post("/internal/token", json=_body())
        client.post("/internal/token", json=_body(client_secret=WRONG_SECRET))
        client.post("/internal/token", json=_body(client_id="ghost"))

        raw = stream.getvalue()
        for forbidden in (
            SHOP_SECRET,
            SHOP_PREVIOUS_SECRET,
            WRONG_SECRET,
            ok.json()["access_token"],
        ):
            assert forbidden not in raw


class TestStartupWithoutKeys:
    def test_the_service_starts_and_answers_health_without_signing_keys(self) -> None:
        with TestClient(create_app()) as bare:
            assert bare.get("/health").status_code == 200
