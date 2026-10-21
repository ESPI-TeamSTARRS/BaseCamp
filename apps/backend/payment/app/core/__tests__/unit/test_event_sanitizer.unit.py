import pytest

from app.core.logging.event_sanitizer import EventSanitizer

MASK = "[masked]"


class TestSensitiveKeys:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "new_password",
            "access_token",
            "Authorization",
            "client_secret",
            "card_number",
            "pan",
            "cvv",
            "idempotency_key",
            "session_cookie",
            "api_key",
        ],
    )
    def test_value_of_a_sensitive_key_is_masked(self, key: str) -> None:
        assert EventSanitizer().attributes({key: "valeur-secrete"}) == {key: MASK}

    @pytest.mark.parametrize(
        "key", ["page_size", "email_hash", "total_cents", "company", "cart_id"]
    )
    def test_ordinary_keys_are_kept(self, key: str) -> None:
        assert EventSanitizer().attributes({key: 12}) == {key: 12}


class TestSensitiveValues:
    def test_an_email_inside_a_text_is_masked(self) -> None:
        cleaned = EventSanitizer().text("contact jean.dupont+x@exemple.fr demande")

        assert cleaned == "contact [email] demande"

    def test_a_valid_card_number_is_masked_with_or_without_separators(self) -> None:
        sanitizer = EventSanitizer()

        assert sanitizer.text("4242 4242 4242 4242") == "[card]"
        assert sanitizer.text("n=4242-4242-4242-4242!") == "n=[card]!"
        assert sanitizer.text("4242424242424242") == "[card]"

    def test_a_long_number_that_is_not_a_card_is_kept(self) -> None:
        assert EventSanitizer().text("1234567890123456") == "1234567890123456"

    def test_a_uuid_is_kept(self) -> None:
        value = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"

        assert EventSanitizer().text(value) == value

    def test_non_text_values_are_untouched(self) -> None:
        assert EventSanitizer().attributes({"line_count": 3, "ok": True, "x": None}) == {
            "line_count": 3,
            "ok": True,
            "x": None,
        }

    def test_text_attributes_are_cleaned(self) -> None:
        assert EventSanitizer().attributes({"note": "a@b.fr"}) == {"note": "[email]"}
