import io
import logging

from app.core.config import Settings
from app.core.logging_setup import install_log_redaction
from app.core.secret_redaction_filter import SecretRedactionFilter

CARD = "4242 4242 4242 4242"
TOKEN = "tok-shop-super-secret-0001"


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, message, args, None)


def _redacted(message: str, *args: object, secrets: tuple[str, ...] = ()) -> str:
    record = _record(message, *args)
    SecretRedactionFilter(secrets).filter(record)
    return record.getMessage()


class TestSecretRedactionFilter:
    def test_known_secrets_are_masked_wherever_they_appear(self) -> None:
        text = _redacted("appel avec %s", f"jeton={TOKEN}", secrets=(TOKEN,))

        assert TOKEN not in text
        assert "[REDACTED]" in text

    def test_bearer_credentials_are_masked_even_when_unknown(self) -> None:
        text = _redacted("Authorization: Bearer abc.DEF-123_xyz== reçu")

        assert "abc.DEF-123_xyz" not in text

    def test_card_numbers_are_masked_with_or_without_separators(self) -> None:
        for card in (CARD, "4242-4242-4242-4242", "4242424242424242", "378282246310005"):
            assert "4242" not in _redacted(f"carte {card} refusée")
            assert "3782" not in _redacted(f"carte {card} refusée")

    def test_sensitive_key_values_are_masked(self) -> None:
        text = _redacted('{"password": "hunter2", "cvv": "123", "api_key": "k-1"} x')

        assert "hunter2" not in text
        assert '"cvv": "123"' not in text
        assert "k-1" not in text

    def test_ordinary_numbers_and_short_secrets_are_left_alone(self) -> None:
        text = _redacted("montant=4990 ordre=CMD-2026-0001 statut=201", secrets=("abc",))

        assert text == "montant=4990 ordre=CMD-2026-0001 statut=201"

    def test_exception_text_is_masked_too(self) -> None:
        try:
            raise RuntimeError(f"échec avec {CARD}")
        except RuntimeError:
            import sys

            record = logging.LogRecord("t", logging.ERROR, __file__, 1, "x", (), sys.exc_info())
        SecretRedactionFilter(()).filter(record)

        assert "4242" not in logging.Formatter().format(record)

    def test_the_filter_never_drops_records(self) -> None:
        assert SecretRedactionFilter(()).filter(_record("ok")) is True


class TestInstallLogRedaction:
    def test_technical_logs_of_the_framework_loggers_are_redacted(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        framework = logging.getLogger("uvicorn.error")
        framework.addHandler(handler)
        try:
            settings = Settings(service_tokens={"shop": TOKEN}, db_password="db-pass-very-secret")
            install_log_redaction(settings)
            install_log_redaction(settings)  # idempotent

            framework.error("jeton %s base %s carte %s", TOKEN, "db-pass-very-secret", CARD)
        finally:
            framework.removeHandler(handler)

        output = stream.getvalue()
        assert "[REDACTED]" in output
        assert TOKEN not in output and "db-pass-very-secret" not in output and "4242" not in output
        assert len([f for f in handler.filters if isinstance(f, SecretRedactionFilter)]) == 1
