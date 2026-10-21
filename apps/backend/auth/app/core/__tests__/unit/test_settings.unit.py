import pytest

from app.core.config import Settings


class TestSettingsDatabaseUrl:
    def test_database_url_is_built_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_DB_HOST", "postgres")
        monkeypatch.setenv("APP_DB_PORT", "5433")
        monkeypatch.setenv("APP_DB_NAME", "auth_db")
        monkeypatch.setenv("APP_DB_USER", "auth_user")
        monkeypatch.setenv("APP_DB_PASSWORD", "p@ss/word")

        url = Settings().database_url

        assert url == "postgresql+psycopg://auth_user:p%40ss%2Fword@postgres:5433/auth_db"

    def test_database_url_has_local_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("HOST", "PORT", "NAME", "USER", "PASSWORD"):
            monkeypatch.delenv(f"APP_DB_{name}", raising=False)

        url = Settings().database_url

        assert url.startswith("postgresql+psycopg://auth:")
        assert url.endswith("@localhost:5432/auth")


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


class TestSettingsServiceTokens:
    def test_defaults_point_to_the_docker_secrets_and_a_sane_rate_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in (
            "JWT_PRIVATE_KEY_FILE",
            "JWT_PUBLIC_KEY_FILE",
            "JWT_ISSUER",
            "SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE",
            "SERVICE_CLIENTS",
        ):
            monkeypatch.delenv(f"APP_{name}", raising=False)

        settings = Settings()

        assert settings.jwt_private_key_file == "/run/secrets/auth_jwt_private_key"
        assert settings.jwt_public_key_file == "/run/secrets/auth_jwt_public_key"
        assert settings.jwt_issuer == "basecamp-auth"
        assert settings.service_token_rate_limit_per_minute == 60
        assert settings.service_clients == {}

    def test_service_clients_are_read_from_a_json_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_SERVICE_CLIENTS", '{"shop": ["payments:write"]}')

        assert Settings().service_clients == {"shop": ["payments:write"]}

    def test_rate_limit_must_be_positive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_SERVICE_TOKEN_RATE_LIMIT_PER_MINUTE", "0")

        with pytest.raises(ValueError, match="greater than 0"):
            Settings()
