from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from app.caller_identity.__tests__.tokens import ADMIN_TOKEN, SHOP_TOKEN
from app.core.config import Settings
from app.intent.infrastructure.models.base import Base
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = SHOP_TOKEN
OTHER_TOKEN = ADMIN_TOKEN
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _headers(key: str = "key-0001", token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"order_reference": "CMD-1", "amount": 2500, "currency": "EUR"}
    body.update(overrides)
    return body


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings()
    application = create_app(settings, engine)
    with TestClient(application) as test_client:
        yield test_client


class TestCreate:
    def test_creates_an_intent_requiring_confirmation(self, client: TestClient) -> None:
        response = client.post("/payments/intents", json=_body(), headers=_headers())

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "requires_confirmation"
        assert body["amount"] == 2500
        assert body["currency"] == "EUR"
        assert body["refunded_amount"] == 0
        assert body["id"]
        assert body["expires_at"]

    def test_replay_with_same_key_and_body_returns_the_same_intent_with_200(
        self, client: TestClient
    ) -> None:
        first = client.post("/payments/intents", json=_body(), headers=_headers())

        second = client.post("/payments/intents", json=_body(), headers=_headers())

        assert second.status_code == 200
        assert second.json() == first.json()

    def test_same_key_with_a_different_body_is_422(self, client: TestClient) -> None:
        client.post("/payments/intents", json=_body(), headers=_headers())

        response = client.post("/payments/intents", json=_body(amount=9000), headers=_headers())

        assert response.status_code == 422

    def test_second_intent_for_the_same_order_is_409(self, client: TestClient) -> None:
        client.post("/payments/intents", json=_body(), headers=_headers())

        response = client.post("/payments/intents", json=_body(), headers=_headers("key-0002"))

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "overrides",
        [
            {"amount": 0},
            {"amount": -5},
            {"amount": 10.5},
            {"amount": "1000"},
            {"amount": True},
            {"amount": 500_001},
            {"currency": "USD"},
            {"order_reference": ""},
            {"order_reference": "a b<script>"},
            {"extra": "field"},
        ],
    )
    def test_invalid_bodies_are_422_with_a_sanitized_message(
        self, client: TestClient, overrides: dict[str, object]
    ) -> None:
        response = client.post("/payments/intents", json=_body(**overrides), headers=_headers())

        assert response.status_code == 422
        assert "script" not in response.text
        assert "input" not in response.text

    def test_idempotency_key_is_mandatory(self, client: TestClient) -> None:
        response = client.post("/payments/intents", json=_body(), headers=AUTH)

        assert response.status_code == 422

    def test_amount_equal_to_the_limit_is_accepted(self, client: TestClient) -> None:
        response = client.post("/payments/intents", json=_body(amount=500_000), headers=_headers())

        assert response.status_code == 201


class TestAuthentication:
    def test_missing_and_invalid_tokens_get_the_same_401(self, client: TestClient) -> None:
        missing = client.post(
            "/payments/intents", json=_body(), headers={"Idempotency-Key": "key-0001"}
        )
        invalid = client.post("/payments/intents", json=_body(), headers=_headers(token="nope"))
        read = client.get("/payments/intents/anything")

        assert missing.status_code == invalid.status_code == read.status_code == 401
        assert missing.content == invalid.content == read.content

    def test_a_non_bearer_scheme_is_refused(self, client: TestClient) -> None:
        response = client.get("/payments/intents/x", headers={"Authorization": f"Basic {TOKEN}"})

        assert response.status_code == 401

    def test_order_reference_is_unique_across_callers(self, client: TestClient) -> None:
        client.post("/payments/intents", json=_body(), headers=_headers())

        response = client.post(
            "/payments/intents", json=_body(), headers=_headers(token=OTHER_TOKEN)
        )

        assert response.status_code == 409


class TestRead:
    def test_reads_an_intent_by_id(self, client: TestClient) -> None:
        created = client.post("/payments/intents", json=_body(), headers=_headers()).json()

        response = client.get(f"/payments/intents/{created['id']}", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == created

    def test_reads_an_intent_by_order_reference(self, client: TestClient) -> None:
        created = client.post("/payments/intents", json=_body(), headers=_headers()).json()

        response = client.get(
            "/payments/intents", params={"order_reference": "CMD-1"}, headers=AUTH
        )

        assert response.status_code == 200
        assert response.json() == created

    @pytest.mark.parametrize(
        "path", ["/payments/intents/00000000-0000-0000-0000-000000000000", "/payments/intents/zzz"]
    )
    def test_unknown_id_is_a_generic_404(self, client: TestClient, path: str) -> None:
        response = client.get(path, headers=AUTH)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}

    def test_unknown_order_reference_is_the_same_generic_404(self, client: TestClient) -> None:
        response = client.get("/payments/intents", params={"order_reference": "x"}, headers=AUTH)

        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}
