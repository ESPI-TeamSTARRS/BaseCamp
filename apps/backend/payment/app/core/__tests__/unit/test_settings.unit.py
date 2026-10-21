import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestSettingsDatabaseUrl:
    def test_database_url_is_built_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DB_HOST", "postgres")
        monkeypatch.setenv("APP_DB_PORT", "5433")
        monkeypatch.setenv("APP_DB_NAME", "payment_db")
        monkeypatch.setenv("APP_DB_USER", "payment_user")
        monkeypatch.setenv("APP_DB_PASSWORD", "p@ss/word")

        url = Settings().database_url

        assert url == "postgresql+psycopg://payment_user:p%40ss%2Fword@postgres:5433/payment_db"

    def test_database_url_has_local_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("HOST", "PORT", "NAME", "USER", "PASSWORD"):
            monkeypatch.delenv(f"APP_DB_{name}", raising=False)

        url = Settings().database_url

        assert url.startswith("postgresql+psycopg://payment:")
        assert url.endswith("@localhost:5432/payment")


class TestSettingsLogPseudonymKey:
    def test_key_is_optional_in_dev_and_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_LOG_PSEUDONYM_KEY", raising=False)
        for environment in ("dev", "local"):
            monkeypatch.setenv("APP_ENVIRONMENT", environment)

            assert Settings().log_pseudonym_key == ""

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_startup_fails_outside_dev_without_the_key(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.delenv("APP_LOG_PSEUDONYM_KEY", raising=False)
        monkeypatch.setenv("APP_ENVIRONMENT", environment)

        with pytest.raises(ValueError, match="APP_LOG_PSEUDONYM_KEY"):
            Settings()

    def test_key_is_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_LOG_PSEUDONYM_KEY", "une-cle-longue-et-secrete")

        assert Settings().log_pseudonym_key == "une-cle-longue-et-secrete"


class TestMetricsSettings:
    def test_the_ledger_lookback_defaults_to_one_day(self) -> None:
        assert Settings().metrics_ledger_lookback_hours == 24

    @pytest.mark.parametrize("hours", [0, 721, -1])
    def test_the_ledger_lookback_is_bounded(self, hours: int) -> None:
        with pytest.raises(ValidationError):
            Settings(metrics_ledger_lookback_hours=hours)
