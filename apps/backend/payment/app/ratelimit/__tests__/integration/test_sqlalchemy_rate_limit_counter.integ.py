from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, StaticPool, create_engine, func, select
from sqlalchemy.orm import Session

from app.ratelimit.infrastructure.models.base import Base
from app.ratelimit.infrastructure.models.rate_limit_window_model import RateLimitWindowModel
from app.ratelimit.infrastructure.repositories.sqlalchemy_rate_limit_counter import (
    SqlAlchemyRateLimitCounter,
)

WINDOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return engine


class TestSqlAlchemyRateLimitCounter:
    def test_hits_are_counted_atomically_per_caller_route_and_window(self, engine: Engine) -> None:
        counter = SqlAlchemyRateLimitCounter(engine)

        counts = [counter.hit("shop", "intents.create", WINDOW) for _ in range(3)]
        other_caller = counter.hit("admin", "intents.create", WINDOW)
        other_route = counter.hit("shop", "intents.read", WINDOW)
        next_window = counter.hit("shop", "intents.create", WINDOW + timedelta(seconds=60))

        assert counts == [1, 2, 3]
        assert (other_caller, other_route, next_window) == (1, 1, 1)

    def test_two_counters_on_the_same_database_share_the_count(self, engine: Engine) -> None:
        first, second = SqlAlchemyRateLimitCounter(engine), SqlAlchemyRateLimitCounter(engine)

        first.hit("shop", "intents.create", WINDOW)

        assert second.hit("shop", "intents.create", WINDOW) == 2

    def test_purge_removes_only_older_windows_of_that_caller_and_route(
        self, engine: Engine
    ) -> None:
        counter = SqlAlchemyRateLimitCounter(engine)
        old, recent = WINDOW - timedelta(seconds=120), WINDOW
        counter.hit("shop", "intents.create", old)
        counter.hit("shop", "intents.create", recent)
        counter.hit("admin", "intents.create", old)

        counter.purge_before("shop", "intents.create", WINDOW - timedelta(seconds=60))

        with Session(engine) as session:
            remaining = session.scalars(
                select(RateLimitWindowModel.caller).order_by(RateLimitWindowModel.caller)
            ).all()
            total = session.scalar(select(func.count()).select_from(RateLimitWindowModel))
        assert remaining == ["admin", "shop"]
        assert total == 2
