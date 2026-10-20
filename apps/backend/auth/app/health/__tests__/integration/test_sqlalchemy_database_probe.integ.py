from sqlalchemy import create_engine

from app.health.infrastructure.clients.sqlalchemy_database_probe import SqlAlchemyDatabaseProbe


class TestSqlAlchemyDatabaseProbe:
    def test_is_available_when_query_succeeds(self) -> None:
        probe = SqlAlchemyDatabaseProbe(create_engine("sqlite+pysqlite:///:memory:"))

        assert probe.is_available() is True

    def test_is_unavailable_when_database_is_unreachable(self) -> None:
        engine = create_engine(
            "postgresql+psycopg://auth:x@127.0.0.1:1/auth", connect_args={"connect_timeout": 1}
        )

        assert SqlAlchemyDatabaseProbe(engine).is_available() is False
