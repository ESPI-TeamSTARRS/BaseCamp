from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.health.domain.interfaces.database_probe import DatabaseProbe


class SqlAlchemyDatabaseProbe(DatabaseProbe):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_available(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True
