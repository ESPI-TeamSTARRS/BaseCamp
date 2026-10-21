import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.service_token.infrastructure.models.base import Base
from app.service_token.infrastructure.models.rate_limit_counter_model import (  # noqa: F401
    RateLimitCounterModel,
)
from app.service_token.infrastructure.models.service_client_model import (  # noqa: F401
    ServiceClientModel,
)

MIGRATION = (
    Path(__file__).resolve().parents[4] / "alembic" / "versions" / "0003_clients_de_service.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0003", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigration0003:
    def test_is_chained_on_0001_and_easy_to_renumber(self) -> None:
        module = _load()

        assert module.revision == "0003"
        assert module.down_revision == "0001"

    def test_creates_the_tables_the_models_expect_and_downgrades_cleanly(self) -> None:
        module = _load()
        engine = create_engine("sqlite+pysqlite://")
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            inspector = inspect(connection)
            for table in Base.metadata.sorted_tables:
                created = {column["name"] for column in inspector.get_columns(table.name)}
                assert created == {column.name for column in table.columns}
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
            assert inspect(connection).get_table_names() == []
