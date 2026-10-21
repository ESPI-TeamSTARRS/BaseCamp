import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.registration.infrastructure.models.auth_base import AuthBase

MIGRATIONS = Path(__file__).resolve().parents[4] / "alembic" / "versions"


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


class TestMigration0004:
    def test_it_follows_the_initial_revision(self) -> None:
        migration = load("0004_users_et_verification")

        assert (migration.revision, migration.down_revision) == ("0004", "0003")

    def test_upgrade_matches_the_sqlalchemy_models(self, engine: Engine) -> None:
        migration = load("0004_users_et_verification")
        with engine.begin() as connection:
            context = MigrationContext.configure(connection, opts={"include_object": _owned})
            with Operations.context(context):
                migration.upgrade()
            differences = compare_metadata(context, AuthBase.metadata)

        assert differences == []

    def test_downgrade_removes_both_tables(self, engine: Engine) -> None:
        migration = load("0004_users_et_verification")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.downgrade()
            assert inspect(connection).get_table_names() == []


def _owned(object_: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """Ne compare que les tables de la migration 0002 (les suivantes ont leur propre test)."""
    table = object_ if type_ == "table" else getattr(object_, "table", None)
    return table is None or table.name in {"users", "email_verification_tokens"}
