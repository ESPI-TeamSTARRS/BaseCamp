"""Transport des emails : défaut SMTP, n8n exige URL et secret, valeur inconnue refusée au démarrage."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

URL = "https://flux.example.test/webhook/send-email"
SHARED_VALUE = "valeur-de-test"


def _settings(**env: str) -> Settings:
    return Settings(**{k.lower(): v for k, v in env.items()})  # type: ignore[arg-type]


class TestMailSettings:
    def test_smtp_is_the_default_and_needs_nothing_else(self) -> None:
        settings = _settings()

        assert settings.mail_transport == "smtp"
        assert (settings.n8n_mail_url, settings.n8n_mail_secret) == ("", "")
        assert settings.n8n_mail_timeout_seconds == 5.0

    def test_n8n_with_its_url_and_secret_is_accepted(self) -> None:
        settings = _settings(mail_transport="n8n", n8n_mail_url=URL, n8n_mail_secret=SHARED_VALUE)

        assert settings.mail_transport == "n8n"

    @pytest.mark.parametrize(
        "extra",
        [{}, {"n8n_mail_url": URL}, {"n8n_mail_secret": SHARED_VALUE}],
    )
    def test_n8n_without_both_url_and_secret_refuses_to_start(self, extra: dict[str, str]) -> None:
        with pytest.raises(ValidationError):
            _settings(mail_transport="n8n", **extra)

    @pytest.mark.parametrize("value", ["", "sendgrid", "N8N", "smtp,n8n"])
    def test_an_unknown_transport_refuses_to_start(self, value: str) -> None:
        with pytest.raises(ValidationError):
            _settings(mail_transport=value)
