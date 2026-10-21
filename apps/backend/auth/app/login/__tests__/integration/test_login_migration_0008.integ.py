from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.login.__tests__.schema import load_migration

NAME = "0008_refresh_rotation"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    yield engine
    engine.dispose()


def _upgrade_to_0007(connection) -> None:  # type: ignore[no-untyped-def]
    load_migration("0004_users_et_verification").upgrade()
    load_migration("0007_login").upgrade()


class TestMigration0008:
    def test_it_follows_revision_0007(self) -> None:
        migration = load_migration(NAME)

        assert (migration.revision, migration.down_revision) == ("0008", "0007")

    def test_it_only_adds_nullable_columns_and_an_index(self, engine: Engine) -> None:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                _upgrade_to_0007(connection)
                before = {c["name"] for c in inspect(connection).get_columns("refresh_tokens")}
                load_migration(NAME).upgrade()
            columns = {c["name"]: c for c in inspect(connection).get_columns("refresh_tokens")}
            indexes = {i["name"] for i in inspect(connection).get_indexes("refresh_tokens")}

        assert set(columns) - before == {"family_id", "used_at"}
        assert columns["family_id"]["nullable"] is True
        assert columns["used_at"]["nullable"] is True
        assert before <= set(columns)
        assert "ix_refresh_tokens_family_id" in indexes

    def test_existing_rows_survive_the_upgrade(self, engine: Engine) -> None:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                _upgrade_to_0007(connection)
                user_id = uuid4().hex
                connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, role, created_at) "
                        "VALUES (:id, 'a@example.com', 'h', 'customer', '2026-01-01 12:00:00')"
                    ),
                    {"id": user_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO refresh_tokens (id, user_id, token_hash, created_at, "
                        "expires_at) VALUES (:id, :user, 'digest', '2026-01-01 12:00:00', "
                        "'2026-01-08 12:00:00')"
                    ),
                    {"id": uuid4().hex, "user": user_id},
                )
                load_migration(NAME).upgrade()
            row = connection.execute(
                text("SELECT token_hash, family_id, used_at FROM refresh_tokens")
            ).one()

        assert tuple(row) == ("digest", None, None)

    def test_downgrade_restores_the_previous_schema(self, engine: Engine) -> None:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                _upgrade_to_0007(connection)
                load_migration(NAME).upgrade()
                load_migration(NAME).downgrade()
            columns = {c["name"] for c in inspect(connection).get_columns("refresh_tokens")}

        assert not {"family_id", "used_at"} & columns
