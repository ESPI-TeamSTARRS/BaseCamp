from typing import Any

import pytest

from app.core.config import Settings
from app.core.database import build_engine


class TestBuildEngine:
    def test_pool_is_bounded_and_recycled(self) -> None:
        settings = Settings(db_pool_size=3, db_max_overflow=2, db_pool_timeout_seconds=1.5)

        engine = build_engine(settings)

        assert engine.pool.size() == 3  # type: ignore[attr-defined]
        assert engine.pool._max_overflow == 2  # type: ignore[attr-defined]
        assert engine.pool._timeout == 1.5  # type: ignore[attr-defined]
        assert engine.pool._recycle == 1800

    def test_connections_have_timeouts_and_errors_hide_sql_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_create_engine(url: str, **kwargs: Any) -> str:
            captured.update(kwargs)
            return "engine"

        monkeypatch.setattr("app.core.database.create_engine", fake_create_engine)

        build_engine(Settings(db_statement_timeout_ms=2500, db_connect_timeout_seconds=2))

        assert captured["hide_parameters"] is True
        assert captured["pool_pre_ping"] is True
        assert captured["connect_args"] == {
            "connect_timeout": 2,
            "options": "-c statement_timeout=2500",
        }

    def test_defaults_are_conservative(self) -> None:
        settings = Settings()

        assert (settings.db_pool_size, settings.db_max_overflow) == (5, 5)
        assert settings.max_body_bytes == 16_384
        assert settings.max_concurrent_requests == 64
        assert settings.rate_limit_window_seconds == 60
