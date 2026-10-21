import pytest
from sqlalchemy import Engine, StaticPool, create_engine

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.service_token import bootstrap
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.models.base import Base
from app.service_token.infrastructure.models.service_client_model import ServiceClientModel  # noqa: F401
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)

SECRET = "bootstrap-secret-" + "s" * 20
EVENTS = InMemoryBusinessEventLogger()
PREVIOUS = "bootstrap-previous-" + "p" * 20


@pytest.fixture
def engine() -> Engine:
    memory = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(memory)
    return memory


def _settings() -> Settings:
    return Settings(service_clients={"shop": ["payments:write"]})


class TestRun:
    def test_registers_declared_clients_with_argon2id_hashes(self, engine: Engine) -> None:
        count = bootstrap.run(
            engine, _settings(), {"APP_SERVICE_CLIENT_SECRET_SHOP": SECRET}, EVENTS
        )

        client = SqlAlchemyServiceClientRepository(engine).find_by_id("shop")
        assert count == 1
        assert client is not None
        assert client.scopes == frozenset({ServiceScope.PAYMENTS_WRITE})
        assert client.current_secret_hash.startswith("$argon2id$")
        assert Argon2SecretHasher().verify(client.current_secret_hash, SECRET)
        assert client.previous_secret_hash is None

    def test_is_replayable_and_supports_rotation(self, engine: Engine) -> None:
        bootstrap.run(engine, _settings(), {"APP_SERVICE_CLIENT_SECRET_SHOP": SECRET}, EVENTS)
        first = SqlAlchemyServiceClientRepository(engine).find_by_id("shop")
        bootstrap.run(engine, _settings(), {"APP_SERVICE_CLIENT_SECRET_SHOP": SECRET}, EVENTS)

        bootstrap.run(
            engine,
            _settings(),
            {
                "APP_SERVICE_CLIENT_SECRET_SHOP": PREVIOUS,
                "APP_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS": SECRET,
            },
            EVENTS,
        )

        client = SqlAlchemyServiceClientRepository(engine).find_by_id("shop")
        assert first is not None
        assert client is not None
        assert client.previous_secret_hash == first.current_secret_hash
        assert Argon2SecretHasher().verify(client.current_secret_hash, PREVIOUS)


class TestMain:
    def test_succeeds_and_reports_the_count(
        self, engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(bootstrap, "create_engine", lambda *_args, **_kwargs: engine)
        monkeypatch.setenv("APP_SERVICE_CLIENTS", '{"shop": ["payments:write"]}')
        monkeypatch.setenv("APP_SERVICE_CLIENT_SECRET_SHOP", SECRET)

        exit_code = bootstrap.main()

        assert exit_code == 0
        assert "1 client(s)" in capsys.readouterr().out

    def test_fails_without_leaking_a_secret_when_the_declaration_is_invalid(
        self, engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(bootstrap, "create_engine", lambda *_args, **_kwargs: engine)
        monkeypatch.setenv("APP_SERVICE_CLIENTS", '{"shop": ["payments:write"]}')
        monkeypatch.setenv("APP_SERVICE_CLIENT_SECRET_SHOP", "too-short")

        exit_code = bootstrap.main()

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "too-short" not in captured.err + captured.out
        assert "shorter than 32" in captured.err
