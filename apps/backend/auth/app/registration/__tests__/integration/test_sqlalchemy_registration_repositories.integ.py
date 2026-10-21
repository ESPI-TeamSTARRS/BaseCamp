from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.registration.domain.entities.user import User
from app.registration.domain.entities.verification_token import VerificationToken
from app.registration.domain.exceptions.email_already_registered_error import (
    EmailAlreadyRegisteredError,
)
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HASH = "a" * 64


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    AuthBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def new_user(email: str = "camille@example.com") -> User:
    return User.register(EmailAddress.of(email), "$argon2id$hash", NOW)


def count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())  # noqa: S608


class TestSqlAlchemyUnitOfWork:
    def test_commit_persists_user_and_token_together(self, engine: Engine) -> None:
        user = new_user()

        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(user)
            work.tokens.add(VerificationToken.issue(user.id, HASH, NOW))
            work.commit()

        assert count(engine, "users") == 1
        assert count(engine, "email_verification_tokens") == 1

    def test_leaving_the_block_without_commit_rolls_back(self, engine: Engine) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(new_user())

        assert count(engine, "users") == 0

    def test_an_error_inside_the_block_rolls_everything_back(self, engine: Engine) -> None:
        user = new_user()

        with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(user)
            work.tokens.add(VerificationToken.issue(user.id, HASH, NOW))
            raise RuntimeError

        assert count(engine, "users") == 0
        assert count(engine, "email_verification_tokens") == 0

    def test_a_duplicate_email_raises_a_domain_error_and_keeps_the_first_account(
        self, engine: Engine
    ) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(new_user())
            work.commit()

        with pytest.raises(EmailAlreadyRegisteredError), SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(new_user())

        assert count(engine, "users") == 1

    def test_user_is_stored_as_an_unverified_customer(self, engine: Engine) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(new_user())
            work.commit()

        with engine.connect() as connection:
            row = connection.execute(text("SELECT email, role, email_verified_at FROM users")).one()

        assert tuple(row) == ("camille@example.com", "customer", None)


class TestVerificationTokens:
    def seed(self, engine: Engine) -> User:
        user = new_user()
        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.add(user)
            work.tokens.add(VerificationToken.issue(user.id, HASH, NOW))
            work.commit()
        return user

    def consume(self, engine: Engine, token_hash: str, now: datetime) -> UUID | None:
        with SqlAlchemyUnitOfWork(engine) as work:
            result = work.tokens.consume(token_hash, now)
            work.commit()
        return result

    def test_a_valid_token_is_consumed_once_and_returns_its_user(self, engine: Engine) -> None:
        user = self.seed(engine)

        first = self.consume(engine, HASH, NOW + timedelta(hours=1))
        second = self.consume(engine, HASH, NOW + timedelta(hours=1))

        assert first == user.id
        assert second is None

    def test_an_expired_token_is_refused(self, engine: Engine) -> None:
        self.seed(engine)

        assert self.consume(engine, HASH, NOW + timedelta(hours=24)) is None

    def test_an_unknown_token_is_refused(self, engine: Engine) -> None:
        self.seed(engine)

        assert self.consume(engine, "b" * 64, NOW) is None

    def test_marking_the_email_verified_keeps_the_first_date(self, engine: Engine) -> None:
        user = self.seed(engine)

        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.mark_email_verified(user.id, NOW + timedelta(hours=1))
            work.users.mark_email_verified(user.id, NOW + timedelta(hours=2))
            work.commit()

        with engine.connect() as connection:
            stored = connection.execute(text("SELECT email_verified_at FROM users")).scalar_one()
        assert str(stored).startswith("2026-01-01 13:00")

    def test_unknown_user_id_is_ignored(self, engine: Engine) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            work.users.mark_email_verified(uuid4(), NOW)
            work.commit()
