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


class TestSettingsLockout:
    def test_the_lockout_has_the_ticket_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("MAX_FAILURES", "WINDOW_SECONDS", "DURATIONS_SECONDS", "MEMORY_SECONDS"):
            monkeypatch.delenv(f"APP_LOCKOUT_{name}", raising=False)

        settings = Settings()

        assert settings.lockout_max_failures == 5
        assert settings.lockout_window_seconds == 900
        assert settings.lockout_durations == (900, 1800, 3600)
        assert settings.lockout_memory_seconds == 86400

    def test_the_policy_is_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_LOCKOUT_MAX_FAILURES", "2")
        monkeypatch.setenv("APP_LOCKOUT_WINDOW_SECONDS", "300")
        monkeypatch.setenv("APP_LOCKOUT_DURATIONS_SECONDS", "300")

        settings = Settings()

        assert (settings.lockout_max_failures, settings.lockout_window_seconds) == (2, 300)
        assert settings.lockout_durations == (300,)

    @pytest.mark.parametrize("value", ["", "abc", "900,-1", "0", "900,,x"])
    def test_invalid_durations_are_refused(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("APP_LOCKOUT_DURATIONS_SECONDS", value)

        with pytest.raises(ValueError, match="APP_LOCKOUT_DURATIONS_SECONDS"):
            Settings()

    @pytest.mark.parametrize("name", ["MAX_FAILURES", "WINDOW_SECONDS", "MEMORY_SECONDS"])
    def test_thresholds_must_be_positive(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        monkeypatch.setenv(f"APP_LOCKOUT_{name}", "0")

        with pytest.raises(ValueError, match=r"greater than"):
            Settings()


class TestSettingsLockoutByStep:
    NAMES = (
        "OPERATOR_PASSWORD_MAX_FAILURES",
        "OPERATOR_PASSWORD_WINDOW_SECONDS",
        "OPERATOR_PASSWORD_DURATION_SECONDS",
        "FACE_MAX_FAILURES",
        "FACE_WINDOW_SECONDS",
        "FACE_DURATION_SECONDS",
        "ADDRESS_MAX_FAILURES",
        "ADDRESS_WINDOW_SECONDS",
        "ADDRESS_DURATION_SECONDS",
    )

    def test_the_steps_have_the_expected_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in self.NAMES:
            monkeypatch.delenv(f"APP_LOCKOUT_{name}", raising=False)

        settings = Settings()

        assert settings.lockout_operator_password_max_failures == 3
        assert settings.lockout_face_max_failures == 5
        assert settings.lockout_operator_password_duration_seconds == 300
        assert settings.lockout_face_duration_seconds == 300
        assert settings.lockout_address_max_failures == 20

    def test_every_step_value_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_LOCKOUT_FACE_MAX_FAILURES", "7")
        monkeypatch.setenv("APP_LOCKOUT_FACE_WINDOW_SECONDS", "120")
        monkeypatch.setenv("APP_LOCKOUT_FACE_DURATION_SECONDS", "60")

        settings = Settings()

        assert (
            settings.lockout_face_max_failures,
            settings.lockout_face_window_seconds,
            settings.lockout_face_duration_seconds,
        ) == (7, 120, 60)

    @pytest.mark.parametrize("name", NAMES)
    def test_a_zero_value_is_refused(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        monkeypatch.setenv(f"APP_LOCKOUT_{name}", "0")

        with pytest.raises(ValueError, match="greater than"):
            Settings()


class TestSettingsTrustedProxies:
    def test_nobody_is_trusted_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_TRUSTED_PROXIES", raising=False)

        assert Settings().trusted_proxies == ""

    def test_the_ranges_are_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_TRUSTED_PROXIES", "172.16.0.0/12,173.245.48.0/20")

        assert Settings().trusted_proxies == "172.16.0.0/12,173.245.48.0/20"

    def test_a_bad_range_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_TRUSTED_PROXIES", "172.16.0.0/12,nope")

        with pytest.raises(ValueError, match="APP_TRUSTED_PROXIES"):
            Settings()


class TestSettingsFaceVerifier:
    def test_the_threshold_defaults_to_the_value_of_the_ai_team(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_FACE_THRESHOLD", raising=False)

        assert Settings().face_threshold == 0.23

    def test_the_threshold_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_FACE_THRESHOLD", "0.31")

        assert Settings().face_threshold == 0.31

    @pytest.mark.parametrize("value", ["0", "1", "-0.2", "1.5", "abc"])
    def test_a_threshold_outside_the_open_unit_interval_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("APP_FACE_THRESHOLD", value)

        with pytest.raises(ValueError, match=r"face_threshold|FACE_THRESHOLD|greater|less|float"):
            Settings()

    def test_the_real_verifier_is_accepted_in_production(self) -> None:
        settings = Settings(
            environment="production",
            log_pseudonym_key="k" * 32,
            backoffice_enabled=True,
            face_verifier="visage-id",
        )

        assert settings.face_verifier == "visage-id"

    def test_the_template_key_comes_from_a_mounted_secret_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_FACE_TEMPLATE_KEY_FILE", raising=False)

        assert Settings().face_template_key_file == "/run/secrets/auth_face_template_key"
