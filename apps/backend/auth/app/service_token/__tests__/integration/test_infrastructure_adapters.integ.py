from datetime import UTC, datetime

import pytest
from argon2 import PasswordHasher
from sqlalchemy import Engine, StaticPool, create_engine, text

from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError
from app.service_token.infrastructure.clients.env_service_client_declarations import (
    EnvServiceClientDeclarations,
)
from app.service_token.infrastructure.clients.system_clock import SystemClock
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.models.base import Base
from app.service_token.infrastructure.repositories.sqlalchemy_rate_limiter import (
    SqlAlchemyRateLimiter,
)
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)

SECRET = "long-enough-secret-" + "e" * 20
# Paramètres minimaux : le test vérifie le format et le comportement, pas le coût de production.
FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture
def engine() -> Engine:
    memory = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(
        memory,
    )
    return memory


def _at(second: int) -> datetime:
    return datetime.fromtimestamp(1_800_000_000 + second, tz=UTC)


class TestArgon2SecretHasher:
    def test_produces_an_argon2id_hash_never_containing_the_secret(self) -> None:
        secret_hash = Argon2SecretHasher(FAST).hash(SECRET)

        assert secret_hash.startswith("$argon2id$")
        assert SECRET not in secret_hash

    def test_hashes_are_salted(self) -> None:
        hasher = Argon2SecretHasher(FAST)

        assert hasher.hash(SECRET) != hasher.hash(SECRET)

    def test_verifies_the_right_secret_only(self) -> None:
        hasher = Argon2SecretHasher(FAST)
        secret_hash = hasher.hash(SECRET)

        assert hasher.verify(secret_hash, SECRET) is True
        assert hasher.verify(secret_hash, SECRET + "x") is False

    def test_an_unreadable_hash_never_matches_and_never_raises(self) -> None:
        assert Argon2SecretHasher(FAST).verify("not-a-hash", SECRET) is False

    def test_uses_the_library_defaults_when_not_configured(self) -> None:
        secret_hash = Argon2SecretHasher().hash(SECRET)

        assert Argon2SecretHasher().verify(secret_hash, SECRET) is True


class TestServiceClientRepository:
    def test_unknown_client_is_none(self, engine: Engine) -> None:
        assert SqlAlchemyServiceClientRepository(engine).find_by_id("ghost") is None

    def test_saves_and_reads_back_a_client(self, engine: Engine) -> None:
        repository = SqlAlchemyServiceClientRepository(engine)
        client = ServiceClient("shop", frozenset({ServiceScope.PAYMENTS_WRITE}), "h1", "h2")

        repository.save(client)

        assert repository.find_by_id("shop") == client

    def test_saving_again_replaces_scopes_and_hashes(self, engine: Engine) -> None:
        repository = SqlAlchemyServiceClientRepository(engine)
        repository.save(ServiceClient("shop", frozenset({ServiceScope.PAYMENTS_WRITE}), "h1", "h2"))

        repository.save(ServiceClient("shop", frozenset(), "h3", None))

        assert repository.find_by_id("shop") == ServiceClient("shop", frozenset(), "h3", None)

    def test_unknown_stored_scopes_grant_nothing(self, engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO service_clients VALUES "
                    "('legacy', 'payments:write retired:scope', 'h1', NULL)"
                )
            )

        client = SqlAlchemyServiceClientRepository(engine).find_by_id("legacy")

        assert client is not None
        assert client.scopes == frozenset({ServiceScope.PAYMENTS_WRITE})


class TestSqlAlchemyRateLimiter:
    def test_allows_up_to_the_limit_then_refuses(self, engine: Engine) -> None:
        limiter = SqlAlchemyRateLimiter(engine, limit_per_window=3)

        decisions = [limiter.hit("shop", _at(1)).allowed for _ in range(5)]

        assert decisions == [True, True, True, False, False]

    def test_counters_are_per_client(self, engine: Engine) -> None:
        limiter = SqlAlchemyRateLimiter(engine, limit_per_window=1)
        limiter.hit("shop", _at(1))

        assert limiter.hit("shop", _at(2)).allowed is False
        assert limiter.hit("billing", _at(2)).allowed is True

    def test_a_new_window_resets_the_counter(self, engine: Engine) -> None:
        limiter = SqlAlchemyRateLimiter(engine, limit_per_window=1)
        limiter.hit("shop", _at(1))
        assert limiter.hit("shop", _at(2)).allowed is False

        assert limiter.hit("shop", _at(61)).allowed is True

    def test_retry_after_is_the_time_left_in_the_window(self, engine: Engine) -> None:
        limiter = SqlAlchemyRateLimiter(engine, limit_per_window=1)
        limiter.hit("shop", _at(0))

        decision = limiter.hit("shop", _at(10))

        window_offset = 1_800_000_000 % 60
        assert decision.retry_after_seconds == 60 - (window_offset + 10) % 60

    def test_counters_are_shared_through_the_database_not_the_instance(
        self, engine: Engine
    ) -> None:
        SqlAlchemyRateLimiter(engine, limit_per_window=1).hit("shop", _at(1))

        assert (
            SqlAlchemyRateLimiter(engine, limit_per_window=1).hit("shop", _at(2)).allowed is False
        )

    def test_old_windows_are_purged(self, engine: Engine) -> None:
        limiter = SqlAlchemyRateLimiter(engine, limit_per_window=5)
        limiter.hit("shop", _at(1))

        limiter.hit("other", _at(300))

        with engine.connect() as connection:
            rows = connection.execute(text("SELECT client_id FROM service_token_rate_limits"))
            assert [row[0] for row in rows] == ["other"]


class TestEnvServiceClientDeclarations:
    def test_reads_current_and_previous_secrets_from_the_environment(self) -> None:
        environ = {
            "APP_SERVICE_CLIENT_SECRET_SHOP": SECRET,
            "APP_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS": SECRET + "-old",
        }

        [declaration] = EnvServiceClientDeclarations(
            {"shop": ["payments:write"]}, environ
        ).list_declarations()

        assert declaration.client_id == "shop"
        assert declaration.scopes == frozenset({ServiceScope.PAYMENTS_WRITE})
        assert declaration.current_secret == SECRET
        assert declaration.previous_secret == SECRET + "-old"

    def test_an_empty_previous_secret_means_none(self) -> None:
        environ = {
            "APP_SERVICE_CLIENT_SECRET_SHOP": SECRET,
            "APP_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS": "",
        }

        [declaration] = EnvServiceClientDeclarations(
            {"shop": ["payments:write"]}, environ
        ).list_declarations()

        assert declaration.previous_secret is None

    def test_a_missing_secret_names_the_variable_without_leaking_anything(self) -> None:
        declarations = EnvServiceClientDeclarations({"shop": ["payments:write"]}, {})

        with pytest.raises(InvalidDeclarationError, match="APP_SERVICE_CLIENT_SECRET_SHOP"):
            declarations.list_declarations()

    def test_an_unknown_scope_is_refused(self) -> None:
        environ = {"APP_SERVICE_CLIENT_SECRET_SHOP": SECRET}

        with pytest.raises(InvalidDeclarationError, match="unknown scope"):
            EnvServiceClientDeclarations({"shop": ["root"]}, environ).list_declarations()

    def test_hyphens_and_dots_in_ids_map_to_underscores(self) -> None:
        environ = {"APP_SERVICE_CLIENT_SECRET_ORDER_WORKER": SECRET}

        [declaration] = EnvServiceClientDeclarations(
            {"order-worker": []}, environ
        ).list_declarations()

        assert declaration.client_id == "order-worker"


class TestSystemClock:
    def test_returns_an_aware_utc_instant(self) -> None:
        assert SystemClock().now().tzinfo is UTC
