from datetime import datetime

from sqlalchemy import Engine, delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.ratelimit.domain.interfaces.rate_limit_counter import RateLimitCounter
from app.ratelimit.infrastructure.models.rate_limit_window_model import RateLimitWindowModel


class SqlAlchemyRateLimitCounter(RateLimitCounter):
    """Compteur partagé : un upsert atomique par requête (Postgres en production, SQLite en test)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def hit(self, caller: str, route: str, window_start: datetime) -> int:
        insert = sqlite_insert if self._engine.dialect.name == "sqlite" else postgres_insert
        statement = insert(RateLimitWindowModel).values(
            caller=caller, route=route, window_start=window_start, hits=1
        )
        upsert = statement.on_conflict_do_update(
            index_elements=["caller", "route", "window_start"],
            set_={"hits": RateLimitWindowModel.hits + 1},
        ).returning(RateLimitWindowModel.hits)
        with self._engine.begin() as connection:
            return int(connection.execute(upsert).scalar_one())

    def purge_before(self, caller: str, route: str, before: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(RateLimitWindowModel).where(
                    RateLimitWindowModel.caller == caller,
                    RateLimitWindowModel.route == route,
                    RateLimitWindowModel.window_start < before,
                )
            )
