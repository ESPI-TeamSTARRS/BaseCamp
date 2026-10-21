import io
import logging

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.logging_setup import install_log_redaction

SECRET = "whsec_settings_0123456789abcdef0123456789abcdef"
PREVIOUS = "whsec_previous_0123456789abcdef0123456789abcdef"


class TestWebhookSettings:
    def test_the_defaults_are_bounded_and_no_secret_is_configured(self) -> None:
        settings = Settings()

        assert settings.webhook_url == ""
        assert settings.webhook_secrets == []
        assert settings.webhook_max_attempts == 6
        assert 0 < settings.webhook_timeout_seconds <= 10

    def test_the_current_secret_signs_first_then_the_previous_one(self) -> None:
        settings = Settings(
            webhook_secret=SecretStr(SECRET), webhook_secret_previous=SecretStr(PREVIOUS)
        )

        assert settings.webhook_secrets == [SECRET, PREVIOUS]

    def test_a_previous_secret_alone_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Settings(webhook_secret_previous=SecretStr(PREVIOUS))

    def test_a_short_secret_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Settings(webhook_secret=SecretStr("too-short"))

    def test_the_secrets_never_appear_in_the_representation(self) -> None:
        settings = Settings(
            webhook_secret=SecretStr(SECRET), webhook_secret_previous=SecretStr(PREVIOUS)
        )

        assert SECRET not in repr(settings)
        assert PREVIOUS not in repr(settings)
        assert SECRET not in settings.model_dump_json()

    @pytest.mark.parametrize("url", ["ftp://shop/hook", "shop:8000/hook", "javascript:alert(1)"])
    def test_only_http_urls_are_accepted(self, url: str) -> None:
        with pytest.raises(ValidationError):
            Settings(webhook_url=url)

    def test_an_http_url_is_accepted(self) -> None:
        assert Settings(webhook_url="http://shop:8000/hook").webhook_url == "http://shop:8000/hook"

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("webhook_max_attempts", 0),
            ("webhook_max_attempts", 100),
            ("webhook_timeout_seconds", 0),
            ("webhook_timeout_seconds", 60),
            ("webhook_backoff_base_seconds", 0),
            ("webhook_poll_interval_seconds", 0),
        ],
    )
    def test_out_of_bound_values_are_refused(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError):
            Settings.model_validate({field: value})


class TestWebhookSecretsAreRedacted:
    def test_a_signing_secret_in_a_technical_log_is_masked(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        framework = logging.getLogger("uvicorn.error")
        framework.addHandler(handler)
        try:
            install_log_redaction(
                Settings(
                    webhook_secret=SecretStr(SECRET), webhook_secret_previous=SecretStr(PREVIOUS)
                )
            )
            framework.error("oups %s puis %s", SECRET, PREVIOUS)
        finally:
            framework.removeHandler(handler)

        assert SECRET not in stream.getvalue()
        assert PREVIOUS not in stream.getvalue()
        assert "[REDACTED]" in stream.getvalue()
