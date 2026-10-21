from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import SchemaItem

from app.login.__tests__.schema import load_migration
from app.login.infrastructure.models.login_base import LoginBase

NAME = "0007_login"


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    yield engine
    engine.dispose()


def _only_declared(
    obj: SchemaItem, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Ignore ce que la tranche ne declare pas (colonnes et tables des autres tranches)."""
    return not (reflected and compare_to is None)


class TestMigration0007:
    def test_it_follows_revision_0006_and_is_additive(self) -> None:
        migration = load_migration(NAME)

        assert (migration.revision, migration.down_revision) == ("0007", "0006")

    def test_upgrade_matches_the_login_models(self, engine: Engine) -> None:
        with engine.begin() as connection:
            context = MigrationContext.configure(
                connection, opts={"include_object": _only_declared}
            )
            with Operations.context(context):
                load_migration("0004_users_et_verification").upgrade()
                load_migration(NAME).upgrade()
            differences = compare_metadata(context, LoginBase.metadata)

        assert differences == []

    def test_upgrade_only_adds_a_nullable_column_and_a_table(self, engine: Engine) -> None:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                load_migration("0004_users_et_verification").upgrade()
                before = {c["name"] for c in inspect(connection).get_columns("users")}
                load_migration(NAME).upgrade()
            columns = {c["name"]: c for c in inspect(connection).get_columns("users")}
            tables = set(inspect(connection).get_table_names())

        assert set(columns) - before == {"disabled_at"}
        assert columns["disabled_at"]["nullable"] is True
        assert before <= set(columns)
        assert {"users", "email_verification_tokens", "refresh_tokens"} <= tables

    def test_downgrade_restores_the_previous_schema(self, engine: Engine) -> None:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                load_migration("0004_users_et_verification").upgrade()
                load_migration(NAME).upgrade()
                load_migration(NAME).downgrade()
            inspector = inspect(connection)

            assert "refresh_tokens" not in inspector.get_table_names()
            assert "disabled_at" not in {c["name"] for c in inspector.get_columns("users")}
