"""API admin des commandes : garde (opérateur + visage), lecture seule, contenu, journaux sans donnée personnelle."""

import io
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event
from sqlalchemy.orm import Session

from app.admin_orders.application.get_admin_order import GetAdminOrderUseCase
from app.admin_orders.application.list_admin_orders import ListAdminOrdersUseCase
from app.admin_orders.infrastructure.repositories.sqlalchemy_admin_order_reader import (
    SqlAlchemyAdminOrderReader,
)
from app.core.logging.email_pseudonymizer import EmailPseudonymizer
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.customer_identity.__tests__.tokens import AUDIENCE, ISSUER, SigningKey
from app.customer_identity.application.authorize_operator import AuthorizeOperatorUseCase
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.jwks_source import JwksSource
from app.customer_identity.infrastructure.clients.jwks_client_token_verifier import (
    JwksClientTokenVerifier,
)
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache
from app.customer_identity.infrastructure.clients.system_clock import SystemClock
from app.main import create_app
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
CORRELATION_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
BASE = "/admin/orders"
AS_OPERATOR = object()  # jeton d'opérateur valide par défaut (None = aucun jeton)
START = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
PAID_ID = "00000000-0000-4000-8000-000000000001"
EMAIL = "camille.martin@example.org"
ADDRESS = "12 rue des Alpes"
FULL_NAME = "Camille Martin"


def _order(index: int, status: str, email: str, number: str) -> OrderModel:
    return OrderModel(
        id=f"00000000-0000-4000-8000-{index:012d}",
        number=number,
        status=status,
        email=email,
        ship_full_name=FULL_NAME,
        ship_line1=ADDRESS,
        ship_line2=None,
        ship_postal_code="38000",
        ship_city="Grenoble",
        ship_country="FR",
        subtotal_cents=7800,
        shipping_cents=490,
        total_cents=8290,
        idempotency_key=f"cle-{index}",
        request_fingerprint="f" * 64,
        created_at=START + timedelta(hours=index),
        user_id=None,
    )


class _Jwks(JwksSource):
    def __init__(self, key: SigningKey) -> None:
        self.keys = {key.kid: key.jwk}
        self.down = False

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        if self.down:
            raise VerificationKeysUnavailableError
        return dict(self.keys)


class _Stack:
    def __init__(self) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        OrderBase.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all(
                [
                    OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=9),
                    _order(1, "paid", EMAIL, "BC-1001"),
                    _order(2, "pending_payment", "autre@example.org", "BC-1002"),
                    _order(3, "expired", "tiers@example.org", "BC-1003"),
                    _order(4, "refunded", "rembourse@example.org", "BC-1004"),
                ]
            )
            session.flush()
            session.add(
                OrderLineModel(
                    order_id=PAID_ID,
                    position=1,
                    product_id="popote",
                    product_name="Popote",
                    unit_price_cents=3900,
                    quantity=2,
                )
            )
            session.commit()
        self.key = SigningKey()
        self.jwks = _Jwks(self.key)
        self.stream = io.StringIO()
        events = StructlogBusinessEventLogger("basecamp-shop", self.stream)
        reader = SqlAlchemyAdminOrderReader(self.engine)
        pseudonymizer = EmailPseudonymizer("cle-de-test-pour-les-empreintes")
        verifier = JwksClientTokenVerifier(
            JwksKeyCache(self.jwks, lambda: 1000.0, 300.0, 10.0), ISSUER, AUDIENCE
        )
        self.application = create_app()
        state = self.application.state
        state.authorize_operator_use_case = AuthorizeOperatorUseCase(
            verifier, SystemClock(), events, "face"
        )
        state.list_admin_orders_use_case = ListAdminOrdersUseCase(reader, events, pseudonymizer)
        state.get_admin_order_use_case = GetAdminOrderUseCase(reader, events, pseudonymizer)

    def token(self, roles: list[str] | None = None, amr: list[str] | None = None) -> str:
        extra: dict[str, Any] = {"roles": roles or ["operator"]}
        extra["amr"] = amr if amr is not None else ["pwd", "face"]
        return self.key.token(extra=extra)

    async def call(self, method: str, path: str, *, token: object | None = AS_OPERATOR) -> Response:
        sent = {"X-Correlation-ID": CORRELATION_ID}
        if token is AS_OPERATOR:
            token = self.token()
        if token:
            sent["Authorization"] = f"Bearer {token}"
        async with AsyncClient(
            transport=ASGITransport(app=self.application), base_url="http://t"
        ) as client:
            return await client.request(method, path, headers=sent)

    def lines(self) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in self.stream.getvalue().splitlines() if line.startswith("{")
        ]


@pytest.fixture
def stack() -> Iterator[_Stack]:
    built = _Stack()
    yield built
    built.engine.dispose()


ROUTES = [("GET", BASE), ("GET", f"{BASE}/{PAID_ID}")]


class TestGuard:
    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_without_a_token_every_route_answers_401(
        self, stack: _Stack, method: str, path: str
    ) -> None:
        response = await stack.call(method, path, token=None)

        assert response.status_code == 401
        assert response.json() == {"detail": "Authentification requise."}
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_a_forged_expired_or_garbage_token_is_a_401(self, stack: _Stack) -> None:
        foreign = SigningKey("autre").token(extra={"roles": ["operator"], "amr": ["face"]})
        expired = stack.key.token(
            issued_at=1.0, lifetime=60, extra={"roles": ["operator"], "amr": ["face"]}
        )

        for token in ("pas.un.jeton", foreign, expired):
            assert (await stack.call("GET", BASE, token=token)).status_code == 401

    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_a_customer_token_answers_403_and_leaks_nothing(
        self, stack: _Stack, method: str, path: str
    ) -> None:
        token = stack.token(roles=["customer"], amr=["pwd", "face"])

        response = await stack.call(method, path, token=token)

        assert response.status_code == 403
        assert response.json() == {"detail": "Acces refuse."}
        assert EMAIL not in response.text

    @pytest.mark.parametrize("amr", [[], ["pwd"], ["pwd", "otp"]])
    @pytest.mark.parametrize(("method", "path"), ROUTES)
    async def test_an_operator_without_the_face_factor_answers_403(
        self, stack: _Stack, method: str, path: str, amr: list[str]
    ) -> None:
        token = stack.token(roles=["operator"], amr=amr)

        response = await stack.call(method, path, token=token)

        assert response.status_code == 403
        assert EMAIL not in response.text

    async def test_the_operator_with_the_face_factor_is_let_in(self, stack: _Stack) -> None:
        assert (await stack.call("GET", BASE)).status_code == 200

    async def test_without_readable_keys_the_answer_is_503_never_an_access(
        self, stack: _Stack
    ) -> None:
        token = stack.token()
        stack.jwks.down = True

        response = await stack.call("GET", BASE, token=token)

        assert response.status_code == 503 and response.headers["retry-after"] == "5"

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    @pytest.mark.parametrize("path", [BASE, f"{BASE}/{PAID_ID}"])
    async def test_nothing_can_be_written(self, stack: _Stack, method: str, path: str) -> None:
        response = await stack.call(method, path)

        assert response.status_code == 405
        statuses = [o["status"] for o in (await stack.call("GET", BASE)).json()["items"]]
        assert sorted(statuses) == ["expired", "paid", "pending_payment", "refunded"]


class TestList:
    async def test_lists_newest_first_with_the_summary_fields(self, stack: _Stack) -> None:
        response = await stack.call("GET", BASE)

        body = response.json()
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert [o["number"] for o in body["items"]] == ["BC-1004", "BC-1003", "BC-1002", "BC-1001"]
        assert (body["total"], body["limit"], body["offset"]) == (4, 20, 0)
        paid = body["items"][3]
        assert paid == {
            "id": PAID_ID,
            "number": "BC-1001",
            "status": "paid",
            "email": EMAIL,
            "total_cents": 8290,
            "item_count": 2,
            "created_at": "2026-10-20T10:00:00",
        }

    async def test_paginates(self, stack: _Stack) -> None:
        body = (await stack.call("GET", f"{BASE}?limit=2&offset=2")).json()

        assert [o["number"] for o in body["items"]] == ["BC-1002", "BC-1001"]
        assert (body["total"], body["limit"], body["offset"]) == (4, 2, 2)

    @pytest.mark.parametrize("status", ["pending_payment", "paid", "expired", "refunded"])
    async def test_filters_by_each_status(self, stack: _Stack, status: str) -> None:
        body = (await stack.call("GET", f"{BASE}?status={status}")).json()

        assert body["total"] == 1 and body["items"][0]["status"] == status

    async def test_searches_by_number_or_email(self, stack: _Stack) -> None:
        by_number = (await stack.call("GET", f"{BASE}?q=BC-1003")).json()
        by_email = (await stack.call("GET", f"{BASE}?q=CAMILLE.martin")).json()

        assert [o["number"] for o in by_number["items"]] == ["BC-1003"]
        assert [o["number"] for o in by_email["items"]] == ["BC-1001"]

    async def test_a_blank_search_is_no_search(self, stack: _Stack) -> None:
        assert (await stack.call("GET", f"{BASE}?q=%20%20")).json()["total"] == 4

    @pytest.mark.parametrize(
        "query",
        ["status=shipped", "limit=0", "limit=101", "offset=-1", f"q={'x' * 101}", "limit=abc"],
    )
    async def test_refuses_a_malformed_query_without_echoing_it(
        self, stack: _Stack, query: str
    ) -> None:
        response = await stack.call("GET", f"{BASE}?{query}")

        assert response.status_code == 422
        assert "shipped" not in response.text

    async def test_the_list_never_carries_the_delivery_address(self, stack: _Stack) -> None:
        text = (await stack.call("GET", BASE)).text

        assert ADDRESS not in text and FULL_NAME not in text and "shipping_address" not in text


class TestDetail:
    async def test_returns_lines_address_totals_and_status(self, stack: _Stack) -> None:
        response = await stack.call("GET", f"{BASE}/{PAID_ID}")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "id": PAID_ID,
            "number": "BC-1001",
            "status": "paid",
            "email": EMAIL,
            "shipping_address": {
                "full_name": FULL_NAME,
                "line1": ADDRESS,
                "line2": None,
                "postal_code": "38000",
                "city": "Grenoble",
                "country": "FR",
            },
            "lines": [
                {
                    "name": "Popote",
                    "unit_price_cents": 3900,
                    "quantity": 2,
                    "line_total_cents": 7800,
                }
            ],
            "subtotal_cents": 7800,
            "shipping_cents": 490,
            "total_cents": 8290,
            "created_at": "2026-10-20T10:00:00",
        }

    async def test_an_unknown_order_is_a_404_with_a_fixed_message(self, stack: _Stack) -> None:
        response = await stack.call("GET", f"{BASE}/00000000-0000-4000-8000-0000000000ff")

        assert (response.status_code, response.json()) == (404, {"detail": "Commande introuvable."})

    async def test_a_malformed_identifier_is_a_422_before_any_lookup(self, stack: _Stack) -> None:
        response = await stack.call("GET", f"{BASE}/pas-un-uuid")

        assert response.status_code == 422
        assert "pas-un-uuid" not in response.text


class TestLogs:
    async def test_events_follow_the_common_contract_without_personal_data(
        self, stack: _Stack
    ) -> None:
        await stack.call("GET", f"{BASE}?q={EMAIL}&status=paid")
        await stack.call("GET", f"{BASE}/{PAID_ID}")
        await stack.call("GET", f"{BASE}/00000000-0000-4000-8000-0000000000ff")

        raw = stack.stream.getvalue()
        assert EMAIL not in raw and ADDRESS not in raw and FULL_NAME not in raw
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        lines = stack.lines()
        for line in lines:
            validator.validate(line)
        names = [(line["event"], line["outcome"]) for line in lines]
        assert ("admin_orders.listed", "success") in names
        assert ("admin_orders.viewed", "success") in names
        assert ("admin_orders.view_denied", "denied") in names
        viewed = next(line for line in lines if line["event"] == "admin_orders.viewed")
        assert viewed["resource_id"] == PAID_ID and viewed["correlation_id"] == CORRELATION_ID
        assert viewed["actor_type"] == "user" and len(viewed["actor_id"]) == 16
