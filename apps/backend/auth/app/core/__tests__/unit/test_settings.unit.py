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


class TestSettingsMail:
    def test_smtp_has_local_mailpit_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("HOST", "PORT", "FROM", "USERNAME", "PASSWORD", "STARTTLS", "TIMEOUT_SECONDS"):
            monkeypatch.delenv(f"APP_SMTP_{name}", raising=False)
        monkeypatch.delenv("APP_PUBLIC_BASE_URL", raising=False)

        settings = Settings()

        assert (settings.smtp_host, settings.smtp_port) == ("localhost", 1025)
        assert settings.smtp_starttls is False
        assert settings.smtp_username == ""
        assert settings.public_base_url == "http://localhost:8080"

    def test_smtp_is_read_from_the_environment_and_the_password_stays_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_SMTP_HOST", "mailpit")
        monkeypatch.setenv("APP_SMTP_PORT", "2525")
        monkeypatch.setenv("APP_SMTP_STARTTLS", "true")
        monkeypatch.setenv("APP_SMTP_USERNAME", "relay")
        monkeypatch.setenv("APP_SMTP_PASSWORD", "tres-secret")

        settings = Settings()

        assert (settings.smtp_host, settings.smtp_port, settings.smtp_starttls) == (
            "mailpit",
            2525,
            True,
        )
        assert settings.smtp_password.get_secret_value() == "tres-secret"
        assert "tres-secret" not in repr(settings)


class TestSettingsClientTokens:
    def test_client_tokens_have_safe_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "JWT_PREVIOUS_PUBLIC_KEYS_DIR",
            "JWT_AUDIENCE",
            "ACCESS_TOKEN_TTL_SECONDS",
            "REFRESH_TOKEN_TTL_SECONDS",
        ):
            monkeypatch.delenv(f"APP_{name}", raising=False)

        settings = Settings()

        assert settings.jwt_previous_public_keys_dir == ""
        assert settings.jwt_audience == "basecamp-client-api"
        assert settings.access_token_ttl_seconds == 900
        assert settings.refresh_token_ttl_seconds == 604800

    @pytest.mark.parametrize("name", ["ACCESS_TOKEN_TTL_SECONDS", "REFRESH_TOKEN_TTL_SECONDS"])
    def test_lifetimes_must_be_positive(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        monkeypatch.setenv(f"APP_{name}", "0")

        with pytest.raises(ValueError, match="greater than 0"):
            Settings()
