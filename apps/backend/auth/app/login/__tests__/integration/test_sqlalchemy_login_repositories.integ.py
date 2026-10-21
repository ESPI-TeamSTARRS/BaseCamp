from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text

from app.login.__tests__.schema import insert_user, migrated_engine
from app.login.domain.entities.refresh_token import RefreshToken
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HASH = "a" * 64


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = migrated_engine()
    yield engine
    engine.dispose()


class TestAccountRepository:
    def test_finds_an_account_by_email_with_its_state(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "$argon2id$x", "operator", False)

        with SqlAlchemyUnitOfWork(engine) as work:
            account = work.accounts.find_by_email("camille@example.com")

        assert account is not None
        assert (account.id, account.email, account.role) == (
            user_id,
            "camille@example.com",
            "operator",
        )
        assert (account.email_verified, account.disabled) == (False, False)
        assert account.password_hash == "$argon2id$x"

    def test_a_disabled_account_is_flagged(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "h", disabled=True)

        with SqlAlchemyUnitOfWork(engine) as work:
            account = work.accounts.find_by_id(user_id)

        assert account is not None
        assert account.disabled is True
        assert account.email_verified is True

    def test_unknown_email_and_id_give_none(self, engine: Engine) -> None:
        with SqlAlchemyUnitOfWork(engine) as work:
            assert work.accounts.find_by_email("personne@example.com") is None
            assert work.accounts.find_by_id(uuid4()) is None

    def test_the_account_repr_hides_the_password_hash(self, engine: Engine) -> None:
        insert_user(engine, uuid4(), "camille@example.com", "$argon2id$secret")

        with SqlAlchemyUnitOfWork(engine) as work:
            account = work.accounts.find_by_email("camille@example.com")

        assert "secret" not in repr(account)

    def test_updating_the_hash_is_committed_with_the_refresh_token(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "ancien")

        with SqlAlchemyUnitOfWork(engine) as work:
            work.accounts.update_password_hash(user_id, "nouveau")
            work.refresh_tokens.add(RefreshToken.issue(user_id, HASH, NOW, 3600))
            work.commit()

        with engine.connect() as connection:
            stored = connection.execute(text("SELECT password_hash FROM users")).scalar_one()
            row = connection.execute(text("SELECT token_hash, user_id FROM refresh_tokens")).one()
        assert stored == "nouveau"
        assert row.token_hash == HASH
        assert row.user_id == user_id.hex

    def test_leaving_the_block_without_commit_rolls_back(self, engine: Engine) -> None:
        user_id = uuid4()
        insert_user(engine, user_id, "camille@example.com", "ancien")

        with SqlAlchemyUnitOfWork(engine) as work:
            work.accounts.update_password_hash(user_id, "nouveau")
            work.refresh_tokens.add(RefreshToken.issue(user_id, HASH, NOW, 3600))

        with engine.connect() as connection:
            assert connection.execute(text("SELECT password_hash FROM users")).scalar_one() == (
                "ancien"
            )
            assert connection.execute(text("SELECT COUNT(*) FROM refresh_tokens")).scalar_one() == 0
