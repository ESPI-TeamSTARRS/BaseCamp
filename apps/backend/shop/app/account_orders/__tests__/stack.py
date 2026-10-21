"""Boutique reelle sur SQLite (commandes, stock) avec identification des clients par JWKS simule."""

import io
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, StaticPool, create_engine, event
from sqlalchemy.orm import Session

from app.account_orders.application.get_my_order import GetMyOrderUseCase
from app.account_orders.application.link_guest_orders import LinkGuestOrdersUseCase
from app.account_orders.application.list_my_orders import ListMyOrdersUseCase
from app.account_orders.domain.entities.account_profile import AccountProfile
from app.account_orders.domain.interfaces.account_profile_directory import AccountProfileDirectory
from app.account_orders.infrastructure.repositories.sqlalchemy_account_order_reader import (
    SqlAlchemyAccountOrderReader,
)
from app.account_orders.infrastructure.repositories.sqlalchemy_guest_order_linker import (
    SqlAlchemyGuestOrderLinker,
)
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.customer_identity.__tests__.tokens import AUDIENCE, ISSUER, SigningKey
from app.customer_identity.application.authenticate_customer import AuthenticateCustomerUseCase
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
from app.order.__tests__.fake_order_unit_of_work import FakePseudonymizer
from app.order.application.place_order import PlaceOrderUseCase
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.repositories.sqlalchemy_order_unit_of_work import (
    SqlAlchemyOrderUnitOfWork,
)
from app.order_tracking.application.lookup_order import LookupOrderUseCase
from app.order_tracking.infrastructure.repositories.sqlalchemy_tracked_order_reader import (
    SqlAlchemyTrackedOrderReader,
)

EMAIL = "camille.martin@example.org"
OTHER_EMAIL = "autre.personne@example.org"
SCHEMA = "docs/development/log-event.schema.json"


class SwitchableJwks(JwksSource):
    def __init__(self, key: SigningKey) -> None:
        self.key = key
        self.down = False
        self.calls = 0

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        self.calls += 1
        if self.down:
            raise VerificationKeysUnavailableError
        return {self.key.kid: self.key.jwk}


class FakeDirectory(AccountProfileDirectory):
    """`auth` simule : profil par jeton; `None` si le compte est inconnu ou `auth` est arrete."""

    def __init__(self) -> None:
        self.profiles: dict[str, AccountProfile] = {}
        self.calls = 0
        self.down = False

    def profile_of(self, token: str) -> AccountProfile | None:
        self.calls += 1
        return None if self.down else self.profiles.get(token)


class Shop:
    def __init__(self) -> None:
        self.engine: Engine = create_engine(
            "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        OrderBase.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all(
                [
                    OrderProductModel(id="tente", name="Tente", price_cents=32900, stock=50),
                    OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=50),
                ]
            )
            session.commit()
        self.key = SigningKey()
        self.jwks = SwitchableJwks(self.key)
        self.directory = FakeDirectory()
        self.log = io.StringIO()
        events = StructlogBusinessEventLogger("basecamp-shop", self.log)
        self.clock_value = 1000.0
        self.application: FastAPI = create_app()
        cache = JwksKeyCache(self.jwks, lambda: self.clock_value, 300.0, 10.0)
        self.application.state.authenticate_customer_use_case = AuthenticateCustomerUseCase(
            JwksClientTokenVerifier(cache, ISSUER, AUDIENCE), SystemClock(), events
        )
        pseudonymizer = FakePseudonymizer()
        self.application.state.place_order_use_case = PlaceOrderUseCase(
            lambda: SqlAlchemyOrderUnitOfWork(self.engine), events, pseudonymizer
        )
        reader = SqlAlchemyAccountOrderReader(self.engine)
        link = LinkGuestOrdersUseCase(
            self.directory, SqlAlchemyGuestOrderLinker(self.engine), events, pseudonymizer
        )
        self.application.state.link_guest_orders_use_case = link
        self.application.state.list_my_orders_use_case = ListMyOrdersUseCase(reader, link, events)
        self.application.state.get_my_order_use_case = GetMyOrderUseCase(reader, events)
        self.application.state.lookup_order_use_case = LookupOrderUseCase(
            SqlAlchemyTrackedOrderReader(self.engine), events, pseudonymizer
        )
        self.counter = 0

    def account(
        self, email: str | None = EMAIL, verified: bool = True, claim_verified: bool | None = None
    ) -> tuple[UUID, dict[str, str]]:
        """Un compte connecte : son identifiant et l'en-tete Bearer d'un jeton signe par `auth`."""
        user = uuid4()
        token = self.key.token(
            user, email_verified=verified if claim_verified is None else claim_verified
        )
        if email is not None:
            self.directory.profiles[token] = AccountProfile(email, verified)
        return user, {"Authorization": f"Bearer {token}"}

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=self.application), base_url="http://t")

    async def order(
        self,
        client: AsyncClient,
        headers: dict[str, str] | None = None,
        email: str = EMAIL,
        item: str = "popote",
    ) -> Any:
        self.counter += 1
        body = {
            "email": email,
            "shippingAddress": {
                "fullName": "Camille Martin",
                "line1": "12 rue des Alpes",
                "postalCode": "38000",
                "city": "Grenoble",
                "country": "FR",
            },
            "lines": [{"productId": item, "quantity": 1}],
        }
        return await client.post(
            "/orders",
            json=body,
            headers={"Idempotency-Key": f"cle-test-{uuid4().hex[:12]}", **(headers or {})},
        )

    def lines(self) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in self.log.getvalue().splitlines() if line.startswith("{")
        ]
