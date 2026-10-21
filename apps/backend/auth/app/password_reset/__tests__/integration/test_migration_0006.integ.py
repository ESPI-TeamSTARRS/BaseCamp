import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.password_reset.infrastructure.models.password_reset_attempt_model import (
    PasswordResetAttemptModel,
)
from app.registration.infrastructure.models.auth_base import AuthBase

MIGRATIONS = Path(__file__).resolve().parents[4] / "alembic" / "versions"
OWNED_TABLES = {"password_reset_tokens", "password_reset_attempts", "session_revocations"}


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, MIGRATIONS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    yield engine
    engine.dispose()


class TestMigration0006:
    def test_it_follows_revision_0004(self) -> None:
        migration = load("0006_reinitialisation_mot_de_passe")

        assert (migration.revision, migration.down_revision) == ("0006", "0004")

    def test_upgrade_matches_the_sqlalchemy_models(self, engine: Engine) -> None:
        base = load("0004_users_et_verification")
        migration = load("0006_reinitialisation_mot_de_passe")
        assert PasswordResetAttemptModel.__tablename__ in AuthBase.metadata.tables
        with engine.begin() as connection:
            context = MigrationContext.configure(connection, opts={"include_object": _owned})
            with Operations.context(context):
                base.upgrade()
                migration.upgrade()
            differences = compare_metadata(context, AuthBase.metadata)

        assert differences == []

    def test_it_only_adds_tables(self, engine: Engine) -> None:
        base = load("0004_users_et_verification")
        migration = load("0006_reinitialisation_mot_de_passe")
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            base.upgrade()
            before = set(inspect(connection).get_table_names())
            migration.upgrade()
            after = set(inspect(connection).get_table_names())

        assert after - before == OWNED_TABLES
        assert before <= after

    def test_downgrade_removes_only_its_tables(self, engine: Engine) -> None:
        base = load("0004_users_et_verification")
        migration = load("0006_reinitialisation_mot_de_passe")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                base.upgrade()
                migration.upgrade()
                migration.downgrade()
            assert set(inspect(connection).get_table_names()) == {
                "users",
                "email_verification_tokens",
            }


def _owned(object_: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Ne compare que les tables de cette migration (les autres ont leur propre test)."""
    table = object_ if type_ == "table" else getattr(object_, "table", None)
    return table is None or table.name in OWNED_TABLES


def test_the_migration_chain_has_a_single_head() -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS.parent))

    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
