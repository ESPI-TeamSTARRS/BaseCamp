from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from app.password_reset.domain.entities.password_reset_token import PasswordResetToken
from app.password_reset.infrastructure.repositories.sqlalchemy_password_reset_unit_of_work import (
    SqlAlchemyPasswordResetUnitOfWork,
)
from app.registration.domain.entities.user import User
from app.registration.domain.value_objects.email_address import EmailAddress
from app.registration.infrastructure.models.auth_base import AuthBase
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EMAIL = EmailAddress.of("camille@example.com")


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    AuthBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def user(engine: Engine) -> User:
    account = User.register(EMAIL, "old-hash", NOW)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.users.add(account)
        work.commit()
    return account


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


class TestAccounts:
    def test_finds_an_account_by_address_and_by_id(self, engine: Engine, user: User) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            by_email = work.accounts.find_by_email(EMAIL)
            by_id = work.accounts.find_by_id(user.id)
            missing = work.accounts.find_by_email(EmailAddress.of("autre@example.com"))
            unknown_id = work.accounts.find_by_id(uuid4())

        assert by_email is not None
        assert by_email == by_id
        assert (by_email.id, by_email.email) == (user.id, EMAIL)
        assert missing is None
        assert unknown_id is None

    def test_changes_only_the_password_hash(self, engine: Engine, user: User) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.accounts.change_password(user.id, "new-hash")
            work.commit()

        assert scalar(engine, "SELECT password_hash FROM users") == "new-hash"
        assert scalar(engine, "SELECT email FROM users") == EMAIL.value


class TestTokens:
    def test_replace_invalidates_the_previous_unused_token(
        self, engine: Engine, user: User
    ) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.tokens.replace(PasswordResetToken.issue(user.id, "a" * 64, NOW), NOW)
            work.tokens.replace(PasswordResetToken.issue(user.id, "b" * 64, NOW), NOW)
            old = work.tokens.consume("a" * 64, NOW)
            new = work.tokens.consume("b" * 64, NOW)

        assert old is None
        assert new == user.id

    def test_consume_is_single_use_and_honours_expiry(self, engine: Engine, user: User) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.tokens.replace(PasswordResetToken.issue(user.id, "a" * 64, NOW), NOW)
            work.commit()
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            late = work.tokens.consume("a" * 64, NOW + timedelta(minutes=30))
            first = work.tokens.consume("a" * 64, NOW + timedelta(minutes=10))
            second = work.tokens.consume("a" * 64, NOW + timedelta(minutes=11))
            unknown = work.tokens.consume("c" * 64, NOW)

        assert (late, first, second, unknown) == (None, user.id, None, None)

    def test_a_rolled_back_transaction_leaves_the_token_usable(
        self, engine: Engine, user: User
    ) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.tokens.replace(PasswordResetToken.issue(user.id, "a" * 64, NOW), NOW)
            work.commit()
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.tokens.consume("a" * 64, NOW)  # pas de commit : annule en sortie
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            again = work.tokens.consume("a" * 64, NOW)

        assert again == user.id


class TestThrottle:
    def test_allows_up_to_the_quota_per_fingerprint_then_refuses(self, engine: Engine) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine, max_requests=2) as work:
            first = work.throttle.allow("fp-1", NOW)
            second = work.throttle.allow("fp-1", NOW)
            third = work.throttle.allow("fp-1", NOW)
            other = work.throttle.allow("fp-2", NOW)

        assert (first, second, third, other) == (True, True, False, True)

    def test_the_window_slides_and_old_attempts_are_purged(self, engine: Engine) -> None:
        window = timedelta(hours=1)
        with SqlAlchemyPasswordResetUnitOfWork(engine, max_requests=1, window=window) as work:
            work.throttle.allow("fp-1", NOW)
            work.commit()
        with SqlAlchemyPasswordResetUnitOfWork(engine, max_requests=1, window=window) as work:
            blocked = work.throttle.allow("fp-1", NOW + timedelta(minutes=59))
            work.commit()
        with SqlAlchemyPasswordResetUnitOfWork(engine, max_requests=1, window=window) as work:
            allowed = work.throttle.allow("fp-1", NOW + timedelta(hours=1, minutes=1))
            work.commit()

        assert (blocked, allowed) == (False, True)
        assert scalar(engine, "SELECT COUNT(*) FROM password_reset_attempts") == 1

    def test_only_a_fingerprint_is_stored(self, engine: Engine) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.throttle.allow("fp-1", NOW)
            work.commit()

        assert scalar(engine, "SELECT email_fingerprint FROM password_reset_attempts") == "fp-1"


class TestSessionRevoker:
    def test_records_then_moves_the_revocation_threshold(self, engine: Engine, user: User) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.sessions.revoke_all(user.id, NOW)
            work.commit()
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.sessions.revoke_all(user.id, NOW + timedelta(hours=2))
            work.commit()

        assert scalar(engine, "SELECT COUNT(*) FROM session_revocations") == 1
        assert str(scalar(engine, "SELECT revoked_at FROM session_revocations")).startswith(
            "2026-01-01 14:00"
        )

    def test_revocation_is_part_of_the_transaction(self, engine: Engine, user: User) -> None:
        with SqlAlchemyPasswordResetUnitOfWork(engine) as work:
            work.sessions.revoke_all(user.id, NOW)

        assert scalar(engine, "SELECT COUNT(*) FROM session_revocations") == 0
