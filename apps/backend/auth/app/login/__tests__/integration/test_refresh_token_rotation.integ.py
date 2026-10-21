from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, text

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.fakes import FakeAccessTokenSigner, FakeClock
from app.login.__tests__.schema import insert_user, load_migration, migrated_engine
from app.login.application.invalid_refresh_token_error import InvalidRefreshTokenError
from app.login.application.refresh_session import RefreshSessionUseCase
from app.login.domain.entities.refresh_token import RefreshToken
from app.login.infrastructure.clients.secure_refresh_token_generator import (
    SecureRefreshTokenGenerator,
)
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HASH = "a" * 64


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = migrated_engine()
    yield engine
    engine.dispose()


def add_token(engine: Engine, token: RefreshToken) -> None:
    with SqlAlchemyUnitOfWork(engine) as work:
        work.refresh_tokens.add(token)
        work.commit()


class TestConsume:
    def test_a_valid_token_is_consumed_once(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        token = RefreshToken.issue(user_id, HASH, NOW, 3600)
        add_token(engine, token)

        with SqlAlchemyUnitOfWork(engine) as work:
            first = work.refresh_tokens.consume(HASH, NOW)
            second = work.refresh_tokens.consume(HASH, NOW)
            work.commit()

        assert first is not None
        assert (first.id, first.family_id, first.used_at) == (token.id, token.family_id, NOW)
        assert second is None

    def test_an_expired_or_unknown_token_is_not_consumed(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        add_token(engine, RefreshToken.issue(user_id, HASH, NOW, 3600))

        with SqlAlchemyUnitOfWork(engine) as work:
            expired = work.refresh_tokens.consume(HASH, NOW + timedelta(hours=1))
            unknown = work.refresh_tokens.consume("b" * 64, NOW)

        assert (expired, unknown) == (None, None)

    def test_a_consumption_is_rolled_back_with_its_transaction(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        add_token(engine, RefreshToken.issue(user_id, HASH, NOW, 3600))

        with SqlAlchemyUnitOfWork(engine) as work:
            work.refresh_tokens.consume(HASH, NOW)

        with SqlAlchemyUnitOfWork(engine) as work:
            assert work.refresh_tokens.consume(HASH, NOW) is not None


class TestFindAndRevoke:
    def test_a_token_without_family_from_before_the_rotation_forms_its_own(
        self, engine: Engine
    ) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        legacy_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO refresh_tokens (id, user_id, token_hash, created_at, "
                    "expires_at) VALUES (:id, :user, :hash, '2026-01-01 12:00:00', "
                    "'2026-01-08 12:00:00')"
                ),
                {"id": legacy_id.hex, "user": user_id.hex, "hash": HASH},
            )

        with SqlAlchemyUnitOfWork(engine) as work:
            found = work.refresh_tokens.find_by_hash(HASH)
            assert found is not None
            assert (found.id, found.family_id, found.used_at) == (legacy_id, legacy_id, None)
            assert work.refresh_tokens.revoke_family(found.family_id) == 1
            work.commit()

        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM refresh_tokens")).scalar_one() == 0

    def test_revoking_a_family_leaves_the_other_families_alone(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        first = RefreshToken.issue(user_id, "1" * 64, NOW, 3600)
        second = first.successor("2" * 64, NOW, 3600)
        other = RefreshToken.issue(user_id, "3" * 64, NOW, 3600)
        for token in (first, second, other):
            add_token(engine, token)

        with SqlAlchemyUnitOfWork(engine) as work:
            revoked = work.refresh_tokens.revoke_family(first.family_id)
            work.commit()

        assert revoked == 2
        with SqlAlchemyUnitOfWork(engine) as work:
            assert work.refresh_tokens.find_by_hash("3" * 64) is not None
            assert work.refresh_tokens.find_by_hash("1" * 64) is None

    def test_an_unknown_hash_is_not_found(self, engine: Engine) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            assert work.refresh_tokens.find_by_hash("z" * 64) is None


class TestConcurrentRefresh:
    def test_of_several_simultaneous_refreshes_with_the_same_token_only_one_succeeds(
        self, tmp_path: Path
    ) -> None:
        engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'auth.db'}")
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            load_migration("0004_users_et_verification").upgrade()
            load_migration("0007_login").upgrade()
            load_migration("0008_refresh_rotation").upgrade()
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h")
        generator = SecureRefreshTokenGenerator()
        raw = generator.generate()
        clock = FakeClock()
        add_token(engine, RefreshToken.issue(user_id, generator.digest(raw), clock.current, 604800))
        use_case = RefreshSessionUseCase(
            lambda: SqlAlchemyUnitOfWork(engine),
            FakeAccessTokenSigner(),
            generator,
            clock,
            InMemoryBusinessEventLogger(),
            900,
            604800,
        )
        contenders = 6
        start = Barrier(contenders)

        def attempt() -> bool:
            start.wait()
            try:
                use_case.execute(raw)
            except InvalidRefreshTokenError:
                return False
            return True

        with ThreadPoolExecutor(contenders) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(contenders)))
        engine.dispose()

        assert outcomes.count(True) == 1
        assert outcomes.count(False) == contenders - 1
